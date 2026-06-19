//! The pure `kind:skill → native form` renderer (plan 02, D14).
//!
//! A SaferSkills skill is a single `SKILL.md` (YAML frontmatter + body, with a
//! `<!-- pointer:start/end -->` block lifted out of the body). Each coding agent
//! consumes a skill differently — this module is the ONE place that maps the
//! canonical `SKILL.md` text to the per-agent native form (design.md §5 matrix):
//!
//! - **Claude Code / OpenClaw** honor the Agent Skills standard → the verbatim
//!   `SKILL.md`, written lazily (loaded on demand), so the FULL body is fine.
//! - **Cursor** → a `.mdc` Agent-Requested rule (loads on match) → FULL body.
//! - **Cline / Windsurf** → always-on rules `.md` → the POINTER only (a <500-line
//!   body injected every turn would pollute their context).
//! - **Codex / Copilot / Gemini** → a marker-delimited block merged into the
//!   shared `AGENTS.md` / `GEMINI.md` (always read) → the POINTER only.
//!
//! Pure + side-effect-free: it takes text + an [`AgentId`] and returns what to
//! write (`File`) or what to merge (`Block`). Placement + disk writes live in the
//! install arms (`writers/mod.rs`).

use crate::agents::AgentId;
use crate::core::error::{SsError, ERR_WRITER_UNSUPPORTED};

/// Marker delimiters for the merged `AGENTS.md` / `GEMINI.md` block (D15). The
/// merge is idempotent because the block between these markers is replaced (not
/// re-appended) on a second apply (`writer::merge_marker_block`).
pub const MARKER_START: &str = "<!-- saferskills:start -->";
pub const MARKER_END: &str = "<!-- saferskills:end -->";

/// The parsed pieces of a `SKILL.md` we need to render every agent's form.
#[derive(Debug)]
struct ParsedSkill {
    /// The frontmatter `description` value (used for the Cursor `.mdc` header).
    description: String,
    /// The body (everything after the closing `---`), pointer block included.
    body: String,
    /// The lifted `<!-- pointer:start/end -->` block's inner text (no markers).
    pointer: String,
}

/// What to write + how to place it for one agent.
pub enum SkillRender {
    /// Write the bytes as a standalone file (verbatim `SKILL.md`, `.mdc`, or a
    /// rules `.md`).
    File { content: String },
    /// Merge the marker block into a shared host file (`AGENTS.md` / `GEMINI.md`).
    Block { block: String },
}

fn render_err(msg: impl Into<String>) -> SsError {
    SsError::new(ERR_WRITER_UNSUPPORTED, msg.into())
}

/// Split `---` YAML frontmatter from the body and lift the
/// `<!-- pointer:start/end -->` block (D13). Frontmatter keys are single-line by
/// contract (plan 01), so a tiny hand-split suffices; only `description` is read.
/// Errors on a missing frontmatter fence or unbalanced pointer markers.
fn parse_skill(skill_md: &str) -> Result<ParsedSkill, SsError> {
    // Frontmatter: the file must open with a `---` fence and close with another.
    let trimmed = skill_md.trim_start_matches('\u{feff}');
    let after_open = trimmed
        .strip_prefix("---\n")
        .or_else(|| trimmed.strip_prefix("---\r\n"))
        .ok_or_else(|| {
            render_err("SKILL.md has no opening `---` frontmatter fence.")
                .with_suggestion("A SaferSkills skill must start with a YAML frontmatter block.")
        })?;
    // Find the closing fence (a line that is exactly `---`).
    let mut fm_lines = Vec::new();
    let mut body_start: Option<usize> = None;
    let mut offset = 0usize;
    for line in after_open.split_inclusive('\n') {
        let stripped = line.trim_end_matches(['\n', '\r']);
        if stripped == "---" {
            body_start = Some(offset + line.len());
            break;
        }
        fm_lines.push(stripped.to_string());
        offset += line.len();
    }
    let Some(body_start) = body_start else {
        return Err(
            render_err("SKILL.md has no closing `---` frontmatter fence.")
                .with_suggestion("A SaferSkills skill must close its YAML frontmatter with `---`."),
        );
    };
    let body = after_open[body_start..]
        .trim_start_matches(['\n', '\r'])
        .to_string();

    // `description:` — single-line key. Value may be quoted ("…") or bare.
    let description = fm_lines
        .iter()
        .find_map(|l| l.trim_start().strip_prefix("description:"))
        .map(|v| {
            let v = v.trim();
            let v = v
                .strip_prefix('"')
                .and_then(|s| s.strip_suffix('"'))
                .unwrap_or(v);
            v.to_string()
        })
        .unwrap_or_default();

    let pointer = extract_pointer(&body)?;
    Ok(ParsedSkill {
        description,
        body,
        pointer,
    })
}

/// Lift the inner text of the `<!-- pointer:start -->` … `<!-- pointer:end -->`
/// block from the body. Errors if a start has no matching end (or vice-versa).
fn extract_pointer(body: &str) -> Result<String, SsError> {
    const PSTART: &str = "<!-- pointer:start -->";
    const PEND: &str = "<!-- pointer:end -->";
    match (body.find(PSTART), body.find(PEND)) {
        (Some(s), Some(e)) if e > s => {
            let inner = &body[s + PSTART.len()..e];
            Ok(inner.trim_matches(['\n', '\r']).to_string())
        }
        (None, None) => Err(
            render_err("SKILL.md has no `<!-- pointer:start/end -->` block.")
                .with_suggestion("The pointer block is what always-injected agents receive."),
        ),
        _ => Err(render_err(
            "SKILL.md has unbalanced `<!-- pointer:start/end -->` markers.",
        )),
    }
}

/// Map the canonical `SKILL.md` text to one agent's native form (design.md §5).
pub fn render_skill(skill_md: &str, agent: AgentId) -> Result<SkillRender, SsError> {
    match agent {
        // Verbatim — Claude Code & OpenClaw honor the Agent Skills standard. Our
        // artifact is a single SKILL.md (D10), written as one file (NOT the buggy
        // unzip tree). The full body is fine — these surfaces load it lazily.
        AgentId::ClaudeCode | AgentId::Openclaw => Ok(SkillRender::File {
            content: skill_md.to_string(),
        }),
        // Cursor `.mdc` — Agent-Requested rule (loads on match) → FULL body.
        AgentId::Cursor => {
            let p = parse_skill(skill_md)?;
            Ok(SkillRender::File {
                content: format!(
                    "---\ndescription: {}\nalwaysApply: false\n---\n\n{}",
                    p.description, p.body
                ),
            })
        }
        // Cline — always-on rules md, POINTER view (D2), no frontmatter.
        AgentId::Cline => {
            let p = parse_skill(skill_md)?;
            Ok(SkillRender::File {
                content: format!("# SaferSkills\n\n{}\n", p.pointer),
            })
        }
        // Windsurf — rules md, POINTER view, model_decision frontmatter, <12 000 chars.
        AgentId::Windsurf => {
            let p = parse_skill(skill_md)?;
            Ok(SkillRender::File {
                content: format!(
                    "---\ntrigger: model_decision\ndescription: Scan AI agent capabilities with SaferSkills before trusting them\n---\n\n# SaferSkills\n\n{}\n",
                    p.pointer
                ),
            })
        }
        // Codex / Copilot / Gemini — marker block merged into AGENTS.md / GEMINI.md
        // (D3/D6/D15), POINTER view. Codex & Copilot produce byte-identical blocks
        // so a shared-project AGENTS.md write is an idempotent no-op replace.
        AgentId::Codex | AgentId::Copilot | AgentId::Gemini => {
            let p = parse_skill(skill_md)?;
            Ok(SkillRender::Block {
                block: format!(
                    "{MARKER_START}\n## SaferSkills\n\n{}\n{MARKER_END}",
                    p.pointer
                ),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The canonical SKILL.md (plan 01), copied verbatim into the test fixtures.
    const FIXTURE: &str = include_str!("../../../tests/fixtures/saferskills.SKILL.md");

    fn file_content(r: SkillRender) -> String {
        match r {
            SkillRender::File { content } => content,
            SkillRender::Block { .. } => panic!("expected File, got Block"),
        }
    }

    fn block_content(r: SkillRender) -> String {
        match r {
            SkillRender::Block { block } => block,
            SkillRender::File { .. } => panic!("expected Block, got File"),
        }
    }

    #[test]
    fn claude_and_openclaw_are_verbatim() {
        assert_eq!(
            file_content(render_skill(FIXTURE, AgentId::ClaudeCode).unwrap()),
            FIXTURE
        );
        assert_eq!(
            file_content(render_skill(FIXTURE, AgentId::Openclaw).unwrap()),
            FIXTURE
        );
    }

    #[test]
    fn cursor_is_mdc_with_full_body() {
        let c = file_content(render_skill(FIXTURE, AgentId::Cursor).unwrap());
        assert!(c.starts_with("---\ndescription: "), "mdc frontmatter: {c}");
        assert!(
            c.contains("\nalwaysApply: false\n---\n"),
            "alwaysApply header"
        );
        // Full body proof — a body-only heading the pointer block does NOT contain.
        assert!(
            c.contains("## Core workflow"),
            "cursor carries the full body"
        );
    }

    #[test]
    fn cline_is_pointer_only() {
        let c = file_content(render_skill(FIXTURE, AgentId::Cline).unwrap());
        assert!(!c.contains("---\n"), "cline has no frontmatter: {c}");
        assert!(
            c.contains("npx saferskills capability"),
            "cline carries the pointer"
        );
        assert!(
            !c.contains("Core workflow"),
            "cline is pointer-only (no full-body sections)"
        );
    }

    #[test]
    fn windsurf_is_model_decision_and_bounded() {
        let c = file_content(render_skill(FIXTURE, AgentId::Windsurf).unwrap());
        assert!(c.contains("trigger: model_decision"), "windsurf trigger");
        assert!(
            c.len() < 12_000,
            "windsurf rule under 12k chars: {}",
            c.len()
        );
        assert!(!c.contains("Core workflow"), "windsurf is pointer-only");
    }

    #[test]
    fn codex_copilot_gemini_are_marker_blocks() {
        let codex = block_content(render_skill(FIXTURE, AgentId::Codex).unwrap());
        let copilot = block_content(render_skill(FIXTURE, AgentId::Copilot).unwrap());
        let gemini = block_content(render_skill(FIXTURE, AgentId::Gemini).unwrap());
        for b in [&codex, &copilot, &gemini] {
            assert!(b.starts_with(MARKER_START), "wrapped in start marker: {b}");
            assert!(
                b.trim_end().ends_with(MARKER_END),
                "wrapped in end marker: {b}"
            );
            assert!(b.contains("## SaferSkills"), "block heading");
        }
        // Codex & Copilot blocks are byte-identical (shared AGENTS.md no-op replace).
        assert_eq!(codex, copilot, "codex == copilot byte-for-byte");
        // Gemini shares the same shape (only the host file differs).
        assert_eq!(codex, gemini, "gemini block == codex block");
    }

    #[test]
    fn parse_skill_errors_on_missing_frontmatter() {
        let err = parse_skill("# No frontmatter\n\nbody").unwrap_err();
        assert_eq!(err.code, ERR_WRITER_UNSUPPORTED);
    }

    #[test]
    fn parse_skill_errors_on_unbalanced_markers() {
        let md = "---\ndescription: x\n---\n\n<!-- pointer:start -->\nonly a start\n";
        let err = parse_skill(md).unwrap_err();
        assert_eq!(err.code, ERR_WRITER_UNSUPPORTED);
    }

    #[test]
    fn parse_skill_reads_quoted_description() {
        let md = "---\nname: x\ndescription: \"Hello world\"\n---\n\n<!-- pointer:start -->\np\n<!-- pointer:end -->\n";
        let p = parse_skill(md).unwrap();
        assert_eq!(p.description, "Hello world");
        assert_eq!(p.pointer, "p");
    }
}
