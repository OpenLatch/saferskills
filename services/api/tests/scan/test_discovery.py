"""Unit tests for capability discovery (pure, no network/DB)."""

from __future__ import annotations

from app.scan.discovery import (
    KIND_HOOK,
    KIND_MCP,
    KIND_PLUGIN,
    KIND_RULES,
    KIND_SKILL,
    discover_capabilities,
)


def _b(text: str) -> bytes:
    return text.encode("utf-8")


def _paths(cap) -> set[str]:
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
