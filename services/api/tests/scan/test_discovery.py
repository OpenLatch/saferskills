"""Unit tests for capability discovery (pure, no network/DB)."""

from __future__ import annotations

from app.scan.discovery import (
    KIND_HOOK,
    KIND_MCP,
    KIND_PLUGIN,
    KIND_RULES,
    KIND_SKILL,
    Capability,
    discover_capabilities,
)


def _b(text: str) -> bytes:
    return text.encode("utf-8")


def _paths(cap: Capability) -> set[str]:
    return {p for p, _ in cap.file_subset}


def test_single_root_skill_is_one_capability() -> None:
    files = [
        ("SKILL.md", _b("---\nname: do-things\n---\n# Do Things")),
        ("scripts/run.sh", _b("echo hi")),
        ("README.md", _b("# readme")),
        ("LICENSE", _b("MIT")),
    ]
    caps = discover_capabilities(files)
    assert len(caps) == 1
    cap = caps[0]
    assert cap.kind == KIND_SKILL
    assert cap.name == "do-things"  # from frontmatter
    assert cap.component_path == ""
    # root component claims everything + repo-wide union (no dupes)
    assert _paths(cap) == {"SKILL.md", "scripts/run.sh", "README.md", "LICENSE"}


def test_zero_capability_fallback_emits_whole_repo_skill() -> None:
    files = [
        ("src/index.ts", _b("export const x = 1")),
        ("package.json", _b('{"name": "plain-lib"}')),
        ("README.md", _b("# plain")),
    ]
    caps = discover_capabilities(files)
    assert len(caps) == 1
    assert caps[0].kind == KIND_SKILL
    assert caps[0].component_path == ""
    assert caps[0].name == ""  # persistence fills repo name
    assert _paths(caps[0]) == {"src/index.ts", "package.json", "README.md"}


def test_multi_capability_repo_discovers_each_kind() -> None:
    files = [
        # 2 skills
        ("skills/alpha/SKILL.md", _b("---\nname: alpha\n---\n")),
        ("skills/alpha/run.py", _b("print('a')")),
        ("skills/beta/SKILL.md", _b("---\nname: beta\n---\n")),
        # mcp server via manifest
        ("servers/gh/mcp.json", _b('{"name": "gh-mcp"}')),
        ("servers/gh/index.js", _b("// server")),
        # 2 hooks
        ("hooks/pre-commit.json", _b('{"command": "x"}')),
        ("hooks/post-merge.json", _b('{"command": "y"}')),
        # plugin
        ("plugin.json", _b('{"name": "the-plugin"}')),
        # rules
        (".cursorrules", _b("be nice")),
        # repo-wide
        ("LICENSE", _b("Apache-2.0")),
        (".github/workflows/ci.yml", _b("on: push")),
    ]
    caps = discover_capabilities(files)
    tally: dict[str, int] = {}
    for c in caps:
        tally[c.kind] = tally.get(c.kind, 0) + 1
    assert tally == {KIND_SKILL: 2, KIND_MCP: 1, KIND_HOOK: 2, KIND_PLUGIN: 1, KIND_RULES: 1}

    alpha = next(c for c in caps if c.kind == KIND_SKILL and c.name == "alpha")
    # alpha owns its subtree, not beta's, plus repo-wide union
    assert "skills/alpha/run.py" in _paths(alpha)
    assert "skills/beta/SKILL.md" not in _paths(alpha)
    assert "LICENSE" in _paths(alpha)
    assert ".github/workflows/ci.yml" in _paths(alpha)

    gh = next(c for c in caps if c.kind == KIND_MCP)
    assert gh.name == "gh-mcp"
    assert "servers/gh/index.js" in _paths(gh)

    hook = next(c for c in caps if c.kind == KIND_HOOK and c.name == "pre-commit")
    # file-based capability: only its own file + repo-wide
    assert _paths(hook) == {"hooks/pre-commit.json", "LICENSE", ".github/workflows/ci.yml"}


def test_deepest_path_claims_file_on_overlap() -> None:
    # An mcp server nested inside a skill dir — the mcp subtree belongs to the
    # mcp capability, not the enclosing skill.
    files = [
        ("pack/SKILL.md", _b("---\nname: pack\n---\n")),
        ("pack/util.py", _b("x = 1")),
        ("pack/mcp/mcp.json", _b('{"name": "inner-mcp"}')),
        ("pack/mcp/server.py", _b("y = 2")),
    ]
    caps = discover_capabilities(files)
    skill = next(c for c in caps if c.kind == KIND_SKILL)
    mcp = next(c for c in caps if c.kind == KIND_MCP)
    assert "pack/util.py" in _paths(skill)
    assert "pack/mcp/server.py" not in _paths(skill)
    assert "pack/mcp/server.py" in _paths(mcp)
    assert "pack/mcp/mcp.json" in _paths(mcp)


def test_name_collision_disambiguated_with_hash_suffix() -> None:
    files = [
        ("a/SKILL.md", _b("---\nname: helper\n---\n")),
        ("b/SKILL.md", _b("---\nname: helper\n---\n")),
    ]
    caps = discover_capabilities(files)
    names = sorted(c.name for c in caps)
    assert len(names) == 2
    assert all(n.startswith("helper-") for n in names), names
    assert names[0] != names[1]


def test_claude_plugin_dir_anchors_plugin() -> None:
    files = [
        ("my-plugin/.claude-plugin/marketplace.json", _b("{}")),
        ("my-plugin/code.js", _b("//")),
    ]
    caps = discover_capabilities(files)
    assert len(caps) == 1
    assert caps[0].kind == KIND_PLUGIN
    assert caps[0].component_path == "my-plugin"


def test_cursor_mdc_rules_each_a_capability() -> None:
    files = [
        (".cursor/rules/style.mdc", _b("style rules")),
        (".cursor/rules/security.mdc", _b("sec rules")),
    ]
    caps = discover_capabilities(files)
    assert {c.kind for c in caps} == {KIND_RULES}
    assert sorted(c.name for c in caps) == ["security", "style"]


def test_package_json_mcp_servers_detected() -> None:
    files = [
        ("package.json", _b('{"name": "srv", "mcpServers": {"a": {}}}')),
    ]
    caps = discover_capabilities(files)
    assert len(caps) == 1
    assert caps[0].kind == KIND_MCP
    assert caps[0].name == "srv"


# ── upload anchorless fan-out (I-3.5) ────────────────────────────────────────


def test_upload_loose_files_fan_into_per_file_capabilities() -> None:
    # Three anchorless loose files — no SKILL.md/mcp.json/hooks dir/etc. As an
    # UPLOAD they each become their own capability (one tab per file).
    files = [
        ("prompt.md", _b("# Prompt\nhello")),
        ("install.sh", _b("#!/bin/sh\necho hi")),
        ("server.json", _b('{"name": "x"}')),
        ("README.md", _b("# readme")),  # repo-wide → unioned into each, not a tab
    ]
    caps = discover_capabilities(files, source_kind="upload")
    by_path = {c.component_path: c for c in caps}
    assert set(by_path) == {"prompt.md", "install.sh", "server.json"}
    # Inferred kinds per name/ext.
    assert by_path["prompt.md"].kind == KIND_SKILL
    assert by_path["install.sh"].kind == KIND_HOOK
    assert by_path["server.json"].kind == KIND_MCP
    # name = file stem; each subset = own file + repo-wide README.
    assert by_path["install.sh"].name == "install"
    assert _paths(by_path["prompt.md"]) == {"prompt.md", "README.md"}


def test_upload_single_loose_file_is_one_capability() -> None:
    caps = discover_capabilities([("notes.md", _b("# hi"))], source_kind="upload")
    assert len(caps) == 1
    assert caps[0].kind == KIND_SKILL
    assert caps[0].component_path == "notes.md"
    assert caps[0].name == "notes"


def test_upload_cursorrules_infers_rules_kind() -> None:
    caps = discover_capabilities(
        [(".cursorrules", _b("be nice")), ("agent.mdc", _b("x"))],
        source_kind="upload",
    )
    assert {c.kind for c in caps} == {KIND_RULES}


def test_upload_all_repo_wide_falls_back_to_single_whole_repo() -> None:
    # No loose file to tab on → keep the single whole-repo fallback (≥1 cap).
    caps = discover_capabilities(
        [("README.md", _b("# hi")), ("LICENSE", _b("MIT"))], source_kind="upload"
    )
    assert len(caps) == 1
    assert caps[0].component_path == ""
    assert caps[0].kind == KIND_SKILL


def test_github_anchorless_repo_still_single_fallback_not_fanned() -> None:
    # The fan-out is UPLOAD-only — a GitHub repo with no anchors stays 1:1.
    files = [
        ("prompt.md", _b("# p")),
        ("install.sh", _b("echo")),
        ("README.md", _b("# r")),
    ]
    caps = discover_capabilities(files)  # source_kind defaults to None (github)
    assert len(caps) == 1
    assert caps[0].component_path == ""


def test_upload_structured_zip_subtree_stays_one_capability() -> None:
    # A `.zip` upload whose files live in a SUBDIRECTORY (a real skill subtree)
    # is NOT flat → normal directory discovery → one capability (SKILL.md + its
    # helper belong together). The flat fan-out must not split a structured zip.
    files = [
        ("skill/SKILL.md", _b("---\nname: real\n---\n")),
        ("skill/run.py", _b("print(1)")),
    ]
    caps = discover_capabilities(files, source_kind="upload")
    assert len(caps) == 1
    assert caps[0].kind == KIND_SKILL
    assert caps[0].name == "real"
    assert caps[0].component_path == "skill"


def test_upload_flat_skill_md_plus_loose_file_fans_out() -> None:
    # The reported bug: uploading SKILL.md + fake.md (both top-level) must give
    # ONE TAB PER FILE — even though SKILL.md is a recognized anchor. The flat
    # batch fans out; SKILL.md keeps its declared frontmatter name (not the stem).
    files = [
        ("SKILL.md", _b("---\nname: canvas-design\n---\n# Canvas Design")),
        ("fake.md", _b("# fake")),
    ]
    caps = discover_capabilities(files, source_kind="upload")
    assert len(caps) == 2
    by_path = {c.component_path: c for c in caps}
    assert by_path["SKILL.md"].name == "canvas-design"  # declared name, not "SKILL"
    assert by_path["SKILL.md"].kind == KIND_SKILL
    assert by_path["fake.md"].name == "fake"


def test_upload_single_flat_skill_md_keeps_declared_name() -> None:
    # A lone flat SKILL.md upload fans to one cap but keeps its frontmatter name
    # (single-file report identity must not regress to the filename stem).
    caps = discover_capabilities(
        [("SKILL.md", _b("---\nname: my-skill\n---\n# X"))], source_kind="upload"
    )
    assert len(caps) == 1
    assert caps[0].kind == KIND_SKILL
    assert caps[0].name == "my-skill"


def test_upload_flat_mcp_json_keeps_declared_name() -> None:
    caps = discover_capabilities(
        [("mcp.json", _b('{"name": "gh-mcp"}')), ("notes.md", _b("# n"))],
        source_kind="upload",
    )
    by_path = {c.component_path: c for c in caps}
    assert by_path["mcp.json"].kind == KIND_MCP
    assert by_path["mcp.json"].name == "gh-mcp"
