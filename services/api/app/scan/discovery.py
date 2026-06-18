"""Capability discovery — split one repo file tree into scannable capabilities.

A single GitHub repo can host several agent capabilities (a Skill, an MCP
server, a couple of Hooks, a Cursor rules set, …). `discover_capabilities`
walks the already-fetched `file_index` (no network) and identifies each
capability's subtree so the engine can score each one independently.

Heuristics are deterministic — every signal is a static file-tree fact, never
content interpretation beyond reading a manifest `name`. The matcher reuses the
engine's glob helpers (`_match_any_glob` / `_fnmatch_recursive`) — there is
exactly one glob implementation in the scan package.

Load-bearing rules (kept stable so scores are reproducible):

1. **Repo-wide files join every capability.** Root `LICENSE` / `README` /
   `SECURITY.md` / `CHANGELOG` / `.github/**` CI files are unioned into every
   capability's `file_subset`, so the kind-scoped maintenance / transparency
   rules (which check for these files) still fire per capability.
2. **Deepest path claims a file on overlap.** A file that sits under two nested
   component directories belongs to the deepest one; a file that is itself a
   file-based capability anchor (a hook json, a rules file) is claimed by that
   capability, not by an enclosing directory capability.
3. **Slug-disambiguate name collisions.** Two capabilities of the same kind that
   resolve to the same name get a `-<hash6>` suffix derived from
   `component_path` so their catalog slugs stay distinct.
4. **Mandatory zero-capability fallback.** A repo where no capability signal
   matches yields exactly one synthetic whole-repo capability (kind inferred,
   default `skill`). Every repo therefore has ≥1 capability — this preserves
   today's 1:1 behaviour for plain single-artifact repos.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

import yaml

from app.scan.engine import match_any_glob

# Kinds match the `catalog_items.kind` enum (snake_case).
KIND_SKILL = "skill"
KIND_MCP = "mcp_server"
KIND_HOOK = "hook"
KIND_PLUGIN = "plugin"
KIND_RULES = "rules"

# Repo-wide files unioned into every capability subset (rule 1). Root-level
# governance/transparency files + the CI tree. Globs are matched with the
# engine's `**`-aware matcher; bare names anchor at the repo root.
_REPO_WIDE_GLOBS: tuple[str, ...] = (
    "LICENSE",
    "LICENSE.*",
    "LICENCE",
    "LICENCE.*",
    "COPYING",
    "COPYING.*",
    "NOTICE",
    "NOTICE.*",
    "README",
    "README.*",
    "SECURITY.md",
    ".github/SECURITY.md",
    "docs/SECURITY.md",
    "CHANGELOG",
    "CHANGELOG.*",
    "CHANGES.md",
    "HISTORY.md",
    "CONTRIBUTING",
    "CONTRIBUTING.*",
    "CODE_OF_CONDUCT.*",
    ".github/**",
)


@dataclass(frozen=True)
class Capability:
    """One scannable capability discovered inside a repo.

    `file_subset` is the slice of the repo the engine scores for this capability
    (its own subtree plus the repo-wide files). `component_path` is the relative
    path that anchors it ("" for a root / whole-repo capability).

    `install_spec` is the per-capability install descriptor the `saferskills`
    install CLI consumes (`build_install_spec`); None for kinds with no config
    (skill / unknown).
    """

    kind: str
    name: str
    component_path: str
    file_subset: list[tuple[str, bytes]]
    install_spec: dict[str, object] | None = None


@dataclass
class _Component:
    """An internal pre-capability anchor before file assignment."""

    kind: str
    name: str
    component_path: str
    is_dir: bool


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _dirname(path: str) -> str:
    posix = _posix(path)
    return posix.rsplit("/", 1)[0] if "/" in posix else ""


def _basename(path: str) -> str:
    return _posix(path).rsplit("/", 1)[-1]


def _stem(path: str) -> str:
    """File stem — basename minus a single trailing extension. Leading-dot files
    (`.cursorrules`) keep their name without the dot."""
    base = _basename(path)
    if base.startswith("."):
        base = base[1:]
    return base.rsplit(".", 1)[0] if "." in base else base


def _frontmatter_name(content: bytes) -> str | None:
    """Read `name:` from a leading YAML frontmatter block, if present."""
    text = content.decode("utf-8", errors="replace")
    if not text.lstrip().startswith("---"):
        return None
    stripped = text.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        return None
    block = stripped[3:end]
    try:
        parsed: object = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if isinstance(parsed, dict):
        value = cast("dict[str, object]", parsed).get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _json_parse(content: bytes) -> dict[str, object] | None:
    """Parse `content` as a JSON object, or None when it is not a JSON dict."""
    try:
        parsed: object = json.loads(content.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def _json_field(content: bytes, field: str) -> object:
    parsed = _json_parse(content)
    return parsed.get(field) if parsed is not None else None


def _json_str(content: bytes, field: str) -> str | None:
    value = _json_field(content, field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_repo_wide(path: str) -> bool:
    return match_any_glob(path, _REPO_WIDE_GLOBS)


# ── anchor detection ───────────────────────────────────────────────────────


def _detect_components(file_index: list[tuple[str, bytes]]) -> list[_Component]:
    """Identify every capability anchor from static file-tree signals.

    Deduped on `(kind, component_path)` — a directory carrying two signals (e.g.
    `mcp.json` + a `package.json` with `mcpServers`) yields one component.
    """
    components: dict[tuple[str, str], _Component] = {}

    def add(kind: str, name: str, component_path: str, *, is_dir: bool) -> None:
        key = (kind, component_path)
        if key in components:
            # Prefer a real (non-empty) name discovered from a manifest.
            if name and not components[key].name:
                components[key].name = name
            return
        components[key] = _Component(kind, name, component_path, is_dir)

    for path, content in file_index:
        posix = _posix(path)
        base = _basename(posix).lower()
        parent = _dirname(posix)
        parent_base = _basename(parent).lower() if parent else ""

        # skill — a directory containing SKILL.md.
        if base == "skill.md":
            name = _frontmatter_name(content) or (_basename(parent) if parent else "")
            add(KIND_SKILL, name, parent, is_dir=True)
            continue

        # mcp_server — mcp.json / .mcp.json manifest.
        if base in ("mcp.json", ".mcp.json"):
            name = _json_str(content, "name") or (_basename(parent) if parent else "")
            add(KIND_MCP, name, parent, is_dir=True)
            continue

        # plugin — plugin.json manifest, or a `.claude-plugin/` directory.
        if base == "plugin.json":
            name = _json_str(content, "name") or (_basename(parent) if parent else "")
            add(KIND_PLUGIN, name, parent, is_dir=True)
            continue
        if ".claude-plugin/" in f"{posix}/":
            # Anchor at the directory that *contains* `.claude-plugin`.
            head = posix.split(".claude-plugin/", 1)[0].rstrip("/")
            add(KIND_PLUGIN, _basename(head) if head else "", head, is_dir=True)
            continue

        # mcp_server — package.json declaring an `mcpServers` block.
        if base == "package.json" and _json_field(content, "mcpServers") is not None:
            name = _json_str(content, "name") or (_basename(parent) if parent else "")
            add(KIND_MCP, name, parent, is_dir=True)
            continue

        # hook — each json under a `hooks/` directory.
        if parent_base == "hooks" and base.endswith(".json"):
            add(KIND_HOOK, _stem(posix), posix, is_dir=False)
            continue

        # hook — a .claude/settings.json declaring a hooks block.
        if posix.endswith(".claude/settings.json") and _json_field(content, "hooks") is not None:
            add(KIND_HOOK, "settings", posix, is_dir=False)
            continue

        # rules — Cursor / Windsurf rule files.
        if base in (".cursorrules", ".windsurfrules"):
            add(KIND_RULES, _stem(posix), posix, is_dir=False)
            continue
        if base.endswith(".mdc") and match_any_glob(posix, ["**/.cursor/rules/*.mdc"]):
            add(KIND_RULES, _stem(posix), posix, is_dir=False)
            continue

    return list(components.values())


def _disambiguate_names(components: list[_Component]) -> None:
    """Rule 3 — append a `component_path` hash suffix to colliding (kind, name)."""
    seen: dict[tuple[str, str], int] = {}
    for comp in components:
        key = (comp.kind, comp.name)
        seen[key] = seen.get(key, 0) + 1
    for comp in components:
        if seen[(comp.kind, comp.name)] > 1:
            suffix = hashlib.sha256(comp.component_path.encode("utf-8")).hexdigest()[:6]
            comp.name = f"{comp.name}-{suffix}" if comp.name else suffix


def _specificity(comp: _Component) -> int:
    """Higher = claims a file more specifically (rule 2). A file-based anchor
    (exact single file) always beats any enclosing directory."""
    if not comp.is_dir:
        return 1_000_000
    if comp.component_path == "":
        return -1  # the whole-repo root loses to any nested directory
    return comp.component_path.count("/") + 1


def _claims(comp: _Component, path: str) -> bool:
    posix = _posix(path)
    if comp.is_dir:
        if comp.component_path == "":
            return True
        return posix == comp.component_path or posix.startswith(comp.component_path + "/")
    return posix == comp.component_path


def _infer_fallback_kind(file_index: list[tuple[str, bytes]]) -> str:
    """Zero-capability fallback kind (rule 4). Default `skill` — the dominant
    single-artifact shape. (Stronger signals would have produced a component.)"""
    return KIND_SKILL


def _infer_file_kind(path: str) -> str:
    """Per-file kind inference for the flat-upload fan-out.

    A loose uploaded file carries no directory anchor, so its kind is inferred
    from its name/extension alone. Mirrors the anchor vocabulary in
    `_detect_components` / `upload.py::_detect` where it can. Default `skill`
    (today's whole-repo fallback kind)."""
    base = _basename(_posix(path)).lower()
    if base in (".cursorrules", ".windsurfrules") or base.endswith((".mdc", ".rules")):
        return KIND_RULES
    if base.endswith(".sh") or "hook" in base:
        return KIND_HOOK
    if base == "server.json" or ("mcp" in base and base.endswith(".json")):
        return KIND_MCP
    # SKILL.md / *.md / everything else → skill (the dominant single-file shape).
    return KIND_SKILL


def _upload_file_kind_name(path: str, content: bytes) -> tuple[str, str]:
    """Per-file (kind, name) for a flat-upload capability.

    A top-level uploaded file that is itself a recognized single-file manifest
    (`SKILL.md`, `mcp.json`, `plugin.json`) keeps its **declared** name (the
    frontmatter / JSON `name`) and kind — so a lone `SKILL.md` upload still reads
    as its real skill name, not the filename stem. Everything else falls back to
    `_infer_file_kind` + the filename stem."""
    base = _basename(_posix(path)).lower()
    stem = _stem(path)
    if base == "skill.md":
        return KIND_SKILL, _frontmatter_name(content) or stem
    if base in ("mcp.json", ".mcp.json"):
        return KIND_MCP, _json_str(content, "name") or stem
    if base == "plugin.json":
        return KIND_PLUGIN, _json_str(content, "name") or stem
    return _infer_file_kind(path), stem


def _upload_loose_fanout(file_index: list[tuple[str, bytes]]) -> list[Capability] | None:
    """Fan a **flat** upload's top-level files into one capability per file.

    "One tab per uploaded file" — each non-repo-wide top-level file becomes its
    own capability (`component_path=<path>`, declared-or-stem `name`, detected
    `kind`) whose `file_subset` is that file unioned with the repo-wide files
    (LICENSE/README/…) so the kind-scoped transparency rules still fire.

    Returns None (→ fall through to normal directory-based discovery) when the
    batch is **not flat** — any non-repo-wide file lives in a subdirectory, i.e.
    a structured `.zip` whose subtree forms a real single capability (a `skill/`
    dir with `SKILL.md` + helpers stays one capability) — or when every file is
    repo-wide (no loose file to tab on → single whole-repo fallback).
    """
    repo_wide = [(p, b) for p, b in file_index if _is_repo_wide(p)]
    repo_wide_paths = {_posix(p) for p, _ in repo_wide}
    loose = [(p, b) for p, b in file_index if _posix(p) not in repo_wide_paths]
    if not loose:
        return None
    # Flat batch only — a nested path signals a structured zip (normal discovery).
    if any("/" in _posix(p) for p, _ in loose):
        return None

    comps: list[_Component] = []
    for path, content in loose:
        kind, name = _upload_file_kind_name(path, content)
        comps.append(_Component(kind, name, path, is_dir=False))
    _disambiguate_names(comps)  # rule 3 — distinct slugs on same-(kind,name) files

    capabilities = [
        Capability(
            kind=comp.kind,
            name=comp.name,
            component_path=comp.component_path,
            file_subset=[(path, content), *repo_wide],
            install_spec=build_install_spec(
                comp.kind, [(path, content), *repo_wide], comp.component_path
            ),
        )
        for comp, (path, content) in zip(comps, loose, strict=True)
    ]
    capabilities.sort(key=lambda c: (c.kind, c.name, c.component_path))
    return capabilities


# ── install-spec extraction (CLI install descriptor) ────────────────────────
#
# The install CLI (`saferskills install`) needs the per-capability config bytes to
# install/uninstall/update across compatible agents. The scan already parses every
# install-relevant byte during discovery; `build_install_spec` re-derives a compact
# descriptor from the SAME already-public bytes (stored-snapshot tier). Keys are
# snake_case to match the wire; the `mcp_entry` value keeps its literal launch-config
# keys (`command`/`args`/`env`/`url`) since the CLI merges it verbatim.

# Closed set of Claude hook event names — used to recognize a bare hook block whose
# top-level keys ARE the events (no enclosing `hooks` wrapper).
_HOOK_EVENTS: frozenset[str] = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "UserPromptSubmit",
        "Notification",
        "Stop",
        "SubagentStop",
        "PreCompact",
        "SessionStart",
        "SessionEnd",
    }
)


def _content_at(file_subset: list[tuple[str, bytes]], path: str) -> bytes | None:
    target = _posix(path)
    for p, content in file_subset:
        if _posix(p) == target:
            return content
    return None


def _content_in_dir(
    file_subset: list[tuple[str, bytes]], component_path: str, basenames: set[str]
) -> bytes | None:
    """First file directly inside `component_path` whose lowercase basename matches."""
    for p, content in file_subset:
        posix = _posix(p)
        if _dirname(posix) == component_path and _basename(posix).lower() in basenames:
            return content
    return None


def _normalize_mcp_entry(obj: object) -> dict[str, object] | None:
    """Reduce a launch object to `{command,args,env}` or `{url}` (CLI merge shape)."""
    if not isinstance(obj, dict):
        return None
    o = cast("dict[str, object]", obj)
    command = o.get("command")
    if isinstance(command, str) and command:
        entry: dict[str, object] = {"command": command}
        args = o.get("args")
        if isinstance(args, list):
            entry["args"] = args
        env = o.get("env")
        if isinstance(env, dict):
            entry["env"] = env
        return entry
    url = o.get("url") or o.get("serverUrl") or o.get("httpUrl")
    if isinstance(url, str) and url:
        return {"url": url}
    return None


def _mcp_entry(
    file_subset: list[tuple[str, bytes]], component_path: str
) -> dict[str, object] | None:
    content = _content_in_dir(
        file_subset, component_path, {"mcp.json", ".mcp.json", "package.json"}
    )
    if content is None:
        return None
    parsed = _json_parse(content)
    if parsed is None:
        return None
    servers = parsed.get("mcpServers")
    if isinstance(servers, dict) and servers:
        first = next(iter(cast("dict[str, object]", servers).values()))
        return _normalize_mcp_entry(first)
    # A direct launch object (`mcp.json` carrying `command`/`url` at top level).
    return _normalize_mcp_entry(parsed)


def _hook_events(file_subset: list[tuple[str, bytes]], component_path: str) -> list[str] | None:
    # A hook capability anchors on a single file (the hook json, or settings.json).
    content = _content_at(file_subset, component_path)
    parsed = _json_parse(content) if content is not None else None
    if parsed is None:
        return None
    block = parsed.get("hooks")
    if isinstance(block, dict):
        events = list(cast("dict[str, object]", block).keys())
    else:
        events = [k for k in parsed if k in _HOOK_EVENTS]
    return events or None


def _plugin_ref(
    file_subset: list[tuple[str, bytes]], component_path: str
) -> dict[str, object] | None:
    content = _content_in_dir(file_subset, component_path, {"plugin.json"})
    if content is None:
        manifest = (
            f"{component_path}/.claude-plugin/plugin.json"
            if component_path
            else ".claude-plugin/plugin.json"
        )
        content = _content_at(file_subset, manifest)
    parsed = _json_parse(content) if content is not None else None
    if parsed is None:
        return None
    name = parsed.get("name")
    version = parsed.get("version")
    return {
        "name": name if isinstance(name, str) and name else None,
        "version": version if isinstance(version, str) and version else None,
        # The marketplace git is not carried in plugin.json; the CLI derives the
        # marketplace cache-dir from the repo coordinates. Kept for forward-compat.
        "marketplace_git": None,
    }


def _rules_files(component_path: str) -> list[dict[str, str]] | None:
    """A rules capability anchors on a single file; classify its source format."""
    base = _basename(_posix(component_path)).lower()
    if base == ".cursorrules":
        target = "cursorrules"
    elif base == ".windsurfrules":
        target = "windsurfrules"
    elif base.endswith(".mdc"):
        target = "cursor_mdc"
    else:
        return None
    return [{"path": _posix(component_path), "target": target}]


def build_install_spec(
    kind: str, file_subset: list[tuple[str, bytes]], component_path: str
) -> dict[str, object] | None:
    """Per-capability install descriptor for the `saferskills` CLI, derived from the
    capability's own scanned bytes. None for kinds with no install config (skill /
    unknown) or when the relevant manifest can't be parsed.
    """
    if kind == KIND_MCP:
        entry = _mcp_entry(file_subset, component_path)
        if entry is None:
            return None
        return {"kind": KIND_MCP, "mcp_entry": entry}
    if kind == KIND_HOOK:
        events = _hook_events(file_subset, component_path)
        if events is None:
            return None
        return {"kind": KIND_HOOK, "hook_events": events}
    if kind == KIND_PLUGIN:
        ref = _plugin_ref(file_subset, component_path)
        if ref is None:
            return None
        return {"kind": KIND_PLUGIN, "plugin_ref": ref}
    if kind == KIND_RULES:
        files = _rules_files(component_path)
        if files is None:
            return None
        return {"kind": KIND_RULES, "rules_files": files}
    return None


def discover_capabilities(
    file_index: list[tuple[str, bytes]], *, source_kind: str | None = None
) -> list[Capability]:
    """Split a repo file tree into one or more scannable capabilities.

    Always returns ≥1 capability — a repo with no capability signal yields a
    single synthetic whole-repo capability (rule 4). For an **upload**
    (`source_kind="upload"`) that is a **flat** batch of top-level files, each
    file is fanned into its own capability (so a multi-file upload renders per-file
    tabs — even when one file is a recognized anchor like `SKILL.md`); a structured
    `.zip` with subdirectories falls through to normal directory-based discovery.
    GitHub scans pass `source_kind=None` → byte-for-byte unchanged.
    """
    if source_kind == "upload":
        fanned = _upload_loose_fanout(file_index)
        if fanned is not None:
            return fanned

    components = _detect_components(file_index)

    if not components:
        kind = _infer_fallback_kind(file_index)
        return [
            Capability(
                kind=kind,
                name="",
                component_path="",
                file_subset=list(file_index),
                install_spec=build_install_spec(kind, list(file_index), ""),
            )
        ]

    _disambiguate_names(components)

    repo_wide = [(p, b) for p, b in file_index if _is_repo_wide(p)]
    repo_wide_paths = {_posix(p) for p, _ in repo_wide}

    # Assign each non-repo-wide file to the most specific component that claims it.
    assigned: dict[int, list[tuple[str, bytes]]] = {id(c): [] for c in components}
    for path, content in file_index:
        if _posix(path) in repo_wide_paths:
            continue
        owner: _Component | None = None
        best = -(10**9)
        for comp in components:
            if _claims(comp, path) and _specificity(comp) > best:
                owner = comp
                best = _specificity(comp)
        if owner is not None:
            assigned[id(owner)].append((path, content))

    capabilities: list[Capability] = []
    for comp in components:
        subset_paths = {_posix(p) for p, _ in assigned[id(comp)]}
        subset = list(assigned[id(comp)])
        # Union the repo-wide files (rule 1), skipping any already present.
        for path, content in repo_wide:
            if _posix(path) not in subset_paths:
                subset.append((path, content))
        capabilities.append(
            Capability(
                kind=comp.kind,
                name=comp.name,
                component_path=comp.component_path,
                file_subset=subset,
                install_spec=build_install_spec(comp.kind, subset, comp.component_path),
            )
        )

    # Deterministic ordering for stable persistence + display.
    capabilities.sort(key=lambda c: (c.kind, c.name, c.component_path))
    return capabilities
