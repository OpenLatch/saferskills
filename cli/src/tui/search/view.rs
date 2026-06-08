//! Ratatui render for the `search` TUI — a pure draw off [`AppState`]. No event
//! handling, no I/O. Honors `NO_COLOR` (the `color` flag) with ASCII glyph
//! fallbacks so the UI reads on a monochrome / dumb terminal.

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap};
use ratatui::Frame;

use crate::api::dto::{CatalogItemSummary, ItemDetailResponse, Severity, Tier};

use super::state::{facet_at, AppState, FacetItem, Focus, AGENTS, FACET_COUNT, KINDS, TIERS};

/// Braille spinner frames (Unicode) and the ASCII fallback.
const SPINNER_UNICODE: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const SPINNER_ASCII: [&str; 4] = ["|", "/", "-", "\\"];

/// Draw the whole UI for one frame. `tick` advances the spinner animation.
pub fn render(frame: &mut Frame, state: &AppState, color: bool, tick: u64) {
    let area = frame.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // query line
            Constraint::Min(5),    // body
            Constraint::Length(2), // footer hints
        ])
        .split(area);

    render_query(frame, rows[0], state, color, tick);

    let body = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(24), // facet sidebar
            Constraint::Min(28),    // result list
            Constraint::Length(40), // preview
        ])
        .split(rows[1]);

    render_facets(frame, body[0], state, color);
    render_list(frame, body[1], state, color);
    render_preview(frame, body[2], state, color);
    render_footer(frame, rows[2], state, color);
}

fn spinner(tick: u64, color: bool) -> &'static str {
    if color {
        SPINNER_UNICODE[(tick as usize) % SPINNER_UNICODE.len()]
    } else {
        SPINNER_ASCII[(tick as usize) % SPINNER_ASCII.len()]
    }
}

fn dim(color: bool) -> Style {
    if color {
        Style::default().fg(Color::DarkGray)
    } else {
        Style::default()
    }
}

fn accent(color: bool) -> Style {
    if color {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().add_modifier(Modifier::BOLD)
    }
}

fn render_query(frame: &mut Frame, area: Rect, state: &AppState, color: bool, tick: u64) {
    let prefix = if state.loading.list {
        format!("{} ", spinner(tick, color))
    } else {
        "› ".to_string()
    };
    let query = if state.query.is_empty() {
        Span::styled("type to search — empty shows trending", dim(color))
    } else {
        Span::raw(state.query.clone())
    };
    let line = Line::from(vec![Span::styled(prefix, accent(color)), query]);
    let focused = state.focus == Focus::Query;
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(border_style(focused, color))
        .title(if focused {
            " Search [focus] "
        } else {
            " Search "
        });
    frame.render_widget(Paragraph::new(line).block(block), area);
}

fn render_facets(frame: &mut Frame, area: Rect, state: &AppState, color: bool) {
    let focused = state.focus == Focus::Filters;
    let cursor = if focused {
        Some(state.facet_cursor.min(FACET_COUNT - 1))
    } else {
        None
    };
    let mut lines: Vec<Line> = Vec::new();
    lines.push(Line::from(Span::styled("KIND", accent(color))));
    for (i, k) in KINDS.iter().enumerate() {
        let idx = flat_index(FacetItem::Kind(i));
        lines.push(facet_line(
            k,
            state.facets.kinds.iter().any(|v| v == k),
            cursor == Some(idx),
            color,
        ));
    }
    lines.push(Line::from(Span::styled("TIER", accent(color))));
    for (i, t) in TIERS.iter().enumerate() {
        let idx = flat_index(FacetItem::Tier(i));
        lines.push(facet_line(
            t,
            state.facets.scan_tiers.iter().any(|v| v == t),
            cursor == Some(idx),
            color,
        ));
    }
    lines.push(Line::from(Span::styled("AGENT", accent(color))));
    for (i, a) in AGENTS.iter().enumerate() {
        let idx = flat_index(FacetItem::Agent(i));
        lines.push(facet_line(
            a,
            state.facets.agents.iter().any(|v| v == a),
            cursor == Some(idx),
            color,
        ));
    }
    let score_idx = flat_index(FacetItem::Score);
    let score_sel = cursor == Some(score_idx);
    let score_prefix = if score_sel { "› " } else { "  " };
    lines.push(Line::from(Span::styled(
        format!("{score_prefix}min score ≥ {}", state.facets.min_score),
        if score_sel { accent(color) } else { dim(color) },
    )));
    lines.push(facet_line(
        "low quality",
        state.facets.show_low_quality,
        cursor == Some(flat_index(FacetItem::LowQuality)),
        color,
    ));

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(border_style(focused, color))
        .title(if focused {
            " Filters [focus] "
        } else {
            " Filters "
        });
    frame.render_widget(Paragraph::new(lines).block(block), area);
}

/// The flattened facet index of a [`FacetItem`] (inverse of `facet_at`).
fn flat_index(item: FacetItem) -> usize {
    (0..FACET_COUNT).find(|i| facet_at(*i) == item).unwrap_or(0)
}

fn facet_line(label: &str, on: bool, selected: bool, color: bool) -> Line<'static> {
    let mark = if on { "[x]" } else { "[ ]" };
    let arrow = if selected { "›" } else { " " };
    let style = if selected {
        accent(color)
    } else if on {
        Style::default()
    } else {
        dim(color)
    };
    Line::from(vec![
        Span::styled(format!("{arrow}{mark} "), style),
        Span::styled(label.to_string(), style),
    ])
}

fn border_style(focused: bool, color: bool) -> Style {
    if focused && color {
        Style::default().fg(Color::Cyan)
    } else if focused {
        Style::default().add_modifier(Modifier::BOLD)
    } else {
        dim(color)
    }
}

fn render_list(frame: &mut Frame, area: Rect, state: &AppState, color: bool) {
    if state.ranked.is_empty() {
        let msg = if state.loading.list {
            "Loading…"
        } else {
            state
                .error
                .as_deref()
                .unwrap_or("No matches. Adjust your query or filters.")
        };
        let block = Block::default().borders(Borders::ALL).title(" Results ");
        frame.render_widget(
            Paragraph::new(Span::styled(msg.to_string(), dim(color))).block(block),
            area,
        );
        return;
    }

    let items: Vec<ListItem> = state
        .ranked
        .iter()
        .filter_map(|i| state.candidates.get(*i))
        .map(|item| ListItem::new(row_line(item, state.is_marked(&item.slug), color)))
        .collect();

    let title = format!(" Results ({}) ", state.ranked.len());
    let block = Block::default().borders(Borders::ALL).title(title);
    let highlight = if color {
        Style::default()
            .bg(Color::Cyan)
            .fg(Color::Black)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default().add_modifier(Modifier::REVERSED)
    };
    let list = List::new(items)
        .block(block)
        .highlight_symbol("› ")
        .highlight_style(highlight);
    let mut list_state = ListState::default();
    list_state.select(Some(
        state.highlight.min(state.ranked.len().saturating_sub(1)),
    ));
    frame.render_stateful_widget(list, area, &mut list_state);
}

fn row_line(item: &CatalogItemSummary, marked: bool, color: bool) -> Line<'static> {
    let check = if marked { "[x] " } else { "[ ] " };
    let tier = item.latest_scan_tier.unwrap_or(Tier::Unscoped);
    let score = item
        .latest_scan_score
        .map(|s| format!("{s:>3}/100"))
        .unwrap_or_else(|| "  —/100".to_string());
    Line::from(vec![
        Span::styled(check.to_string(), accent(color)),
        Span::styled(format!("{} ", tier_glyph(tier)), tier_style(tier, color)),
        Span::raw(format!("{:<28} ", truncate(&item.display_name, 28))),
        Span::styled(score, score_style(item.latest_scan_score, color)),
        Span::styled(format!("  {}", kind_short(&item.kind)), dim(color)),
    ])
}

fn render_preview(frame: &mut Frame, area: Rect, state: &AppState, color: bool) {
    let block = Block::default().borders(Borders::ALL).title(" Preview ");
    let Some(item) = state.highlighted() else {
        frame.render_widget(
            Paragraph::new(Span::styled("—", dim(color))).block(block),
            area,
        );
        return;
    };

    let mut lines: Vec<Line> = Vec::new();
    lines.push(Line::from(Span::styled(
        item.display_name.clone(),
        accent(color),
    )));
    lines.push(Line::from(Span::styled(
        format!("{} · {}", kind_short(&item.kind), item.slug),
        dim(color),
    )));
    lines.push(Line::raw(""));

    if let Some(detail) = state.current_preview() {
        render_preview_detail(&mut lines, detail, color);
    } else if state.loading.preview {
        lines.push(Line::from(Span::styled("Loading details…", dim(color))));
    } else if let Some(desc) = item.description.as_deref() {
        lines.push(Line::from(Span::raw(truncate(desc, 200))));
    }

    frame.render_widget(
        Paragraph::new(lines).wrap(Wrap { trim: true }).block(block),
        area,
    );
}

fn render_preview_detail(lines: &mut Vec<Line>, detail: &ItemDetailResponse, color: bool) {
    let score = detail
        .item
        .latest_scan_score
        .or_else(|| detail.latest_scan.as_ref().map(|s| s.aggregate_score));
    let tier = detail
        .item
        .latest_scan_tier
        .or_else(|| detail.latest_scan.as_ref().map(|s| s.tier))
        .unwrap_or(Tier::Unscoped);
    let score_str = score
        .map(|s| format!("{s}/100"))
        .unwrap_or_else(|| "—".into());
    lines.push(Line::from(vec![
        Span::styled(format!("{} ", tier_glyph(tier)), tier_style(tier, color)),
        Span::styled(
            format!("{} {score_str}", tier.label()),
            tier_style(tier, color),
        ),
    ]));

    if let Some(scan) = detail.latest_scan.as_ref() {
        if !scan.sub_scores.is_empty() {
            lines.push(Line::raw(""));
            for (key, label) in crate::cli::color::AXES {
                if let Some(v) = scan.sub_scores.get(key) {
                    lines.push(Line::from(Span::raw(format!(
                        "  {label:<13} {}",
                        gauge(*v)
                    ))));
                }
            }
        }
        let mut findings = scan.findings.clone();
        findings.sort_by_key(|f| std::cmp::Reverse(f.severity.rank()));
        if !findings.is_empty() {
            lines.push(Line::raw(""));
            lines.push(Line::from(Span::styled(
                format!("{} finding(s):", findings.len()),
                dim(color),
            )));
            for f in findings.iter().take(4) {
                let title = f.title.clone().unwrap_or_else(|| f.rule_id.clone());
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("  {} ", severity_glyph(f.severity)),
                        severity_style(f.severity, color),
                    ),
                    Span::raw(truncate(&title, 30)),
                ]));
            }
        } else {
            lines.push(Line::raw(""));
            lines.push(Line::from(Span::styled("No findings.", dim(color))));
        }
    } else {
        lines.push(Line::raw(""));
        lines.push(Line::from(Span::styled("Not scanned yet.", dim(color))));
    }
}

fn render_footer(frame: &mut Frame, area: Rect, state: &AppState, color: bool) {
    let marked = state.marked.len();
    let hint = match state.focus {
        Focus::Query => {
            "↑↓ move · Tab mark · Enter install · Ctrl-F filters · Esc cancel".to_string()
        }
        Focus::Filters => {
            "↑↓ facet · Space toggle · ←→ score · Tab/Ctrl-F query · Esc back".to_string()
        }
    };
    let hint = if state.is_truncated() {
        format!(
            "top {} of {} — refine · {hint}",
            state.candidates.len(),
            state.total_count
        )
    } else {
        hint
    };
    let lines = vec![
        Line::from(Span::styled(
            format!("{marked} marked for install"),
            accent(color),
        )),
        Line::from(Span::styled(hint, dim(color))),
    ];
    frame.render_widget(Paragraph::new(lines), area);
}

// ─── small render helpers (pure) ──────────────────────────────────────────────

fn gauge(score: i64) -> String {
    let s = score.clamp(0, 100) as usize;
    let filled = ((s * 10) + 50) / 100;
    let filled = filled.min(10);
    format!("{}{} {s}", "█".repeat(filled), "░".repeat(10 - filled))
}

fn kind_short(kind: &str) -> &str {
    match kind {
        "skill" => "Skill",
        "mcp_server" => "MCP",
        "hook" => "Hook",
        "plugin" => "Plugin",
        "rules" => "Rules",
        other => other,
    }
}

fn tier_glyph(tier: Tier) -> &'static str {
    match tier {
        Tier::Green => "●",
        Tier::Yellow => "◐",
        Tier::Orange => "◑",
        Tier::Red => "✗",
        Tier::Unscoped | Tier::Unknown => "○",
    }
}

fn tier_style(tier: Tier, color: bool) -> Style {
    if !color {
        return Style::default();
    }
    match tier {
        Tier::Green => Style::default().fg(Color::Green),
        Tier::Yellow | Tier::Orange => Style::default().fg(Color::Yellow),
        Tier::Red => Style::default().fg(Color::Red),
        Tier::Unscoped | Tier::Unknown => Style::default().fg(Color::DarkGray),
    }
}

fn score_style(score: Option<u8>, color: bool) -> Style {
    if !color {
        return Style::default();
    }
    match score {
        Some(s) if s >= 80 => Style::default().fg(Color::Green),
        Some(s) if s >= 60 => Style::default().fg(Color::Yellow),
        Some(s) if s >= 40 => Style::default().fg(Color::Rgb(255, 165, 0)),
        Some(_) => Style::default().fg(Color::Red),
        None => Style::default().fg(Color::DarkGray),
    }
}

fn severity_glyph(sev: Severity) -> &'static str {
    match sev {
        Severity::Critical => "✗",
        Severity::High => "▲",
        Severity::Medium => "◆",
        Severity::Low => "·",
        Severity::Info | Severity::Unknown => "ⓘ",
    }
}

fn severity_style(sev: Severity, color: bool) -> Style {
    if !color {
        return Style::default();
    }
    match sev {
        Severity::Critical | Severity::High => Style::default().fg(Color::Red),
        Severity::Medium | Severity::Low => Style::default().fg(Color::Yellow),
        Severity::Info | Severity::Unknown => Style::default().fg(Color::DarkGray),
    }
}

/// Truncate to `w` display chars, ending in `…` when cut.
fn truncate(s: &str, w: usize) -> String {
    let n = s.chars().count();
    if n <= w {
        s.to_string()
    } else {
        let cut: String = s.chars().take(w.saturating_sub(1)).collect();
        format!("{cut}…")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gauge_fills_proportionally() {
        assert!(gauge(0).starts_with("░"));
        assert!(gauge(100).starts_with("██████████"));
        assert_eq!(gauge(60).matches('█').count(), 6);
    }

    #[test]
    fn truncate_adds_ellipsis_only_when_cut() {
        assert_eq!(truncate("short", 10), "short");
        assert_eq!(truncate("abcdefghij", 5), "abcd…");
    }

    #[test]
    fn kind_short_maps() {
        assert_eq!(kind_short("mcp_server"), "MCP");
        assert_eq!(kind_short("skill"), "Skill");
        assert_eq!(kind_short("other"), "other");
    }

    #[test]
    fn spinner_cycles_per_color_mode() {
        assert_eq!(spinner(0, false), "|");
        assert_eq!(spinner(4, false), "|"); // wraps at 4
        assert_eq!(spinner(0, true), "⠋");
    }

    #[test]
    fn glyphs_distinct_per_tier() {
        assert_ne!(tier_glyph(Tier::Green), tier_glyph(Tier::Red));
        assert_eq!(tier_glyph(Tier::Unscoped), tier_glyph(Tier::Unknown));
    }

    // ─── full-render coverage via the headless TestBackend ─────────────────────

    use crate::api::dto::{
        CatalogListEnvelope, EvidenceExcerpt, FindingResponse, ItemDetailResponse, ScanReportDetail,
    };
    use crate::tui::search::state::{AppState, Facets};
    use ratatui::backend::TestBackend;
    use ratatui::Terminal;

    fn item(slug: &str, kind: &str, name: &str, score: Option<u8>) -> CatalogItemSummary {
        CatalogItemSummary {
            id: slug.into(),
            slug: slug.into(),
            kind: kind.into(),
            display_name: name.into(),
            description: Some("A useful capability for testing.".into()),
            github_url: None,
            github_org: None,
            github_repo: None,
            source_kind: None,
            popularity_tier: "emerging".into(),
            popularity_score: 10,
            latest_scan_score: score,
            latest_scan_tier: score.map(|s| {
                if s >= 80 {
                    Tier::Green
                } else if s >= 60 {
                    Tier::Yellow
                } else if s >= 40 {
                    Tier::Orange
                } else {
                    Tier::Red
                }
            }),
            latest_scan_at: None,
            findings_count: 0,
            registries: vec![],
            agent_compatibility: vec![],
            updated_at: None,
        }
    }

    fn envelope(items: Vec<CatalogItemSummary>, total: i64) -> CatalogListEnvelope {
        CatalogListEnvelope {
            data: items,
            next_cursor: None,
            total_count: total,
            page: 1,
            total_pages: 1,
            page_size: 50,
        }
    }

    fn finding(sev: Severity) -> FindingResponse {
        FindingResponse {
            id: "f".into(),
            rule_id: "SS-MCP-RULE-01".into(),
            severity: sev,
            sub_score: "security".into(),
            penalty: 10,
            status_at_scan: "active".into(),
            file_path: "server.py".into(),
            line_start: 1,
            line_end: None,
            matched_content_sha256: "0".repeat(64),
            remediation_link: "https://x".into(),
            rubric_version: "v3".into(),
            evidence_excerpt: Some(EvidenceExcerpt {
                file: "server.py".into(),
                lang: None,
                lines: vec![],
                truncated: false,
            }),
            title: Some("Poisoned tool description".into()),
            explanation: None,
            category_label: None,
            severity_rationale: None,
            remediation: None,
        }
    }

    fn detail(score: u8, tier: Tier, with_findings: bool, with_scan: bool) -> ItemDetailResponse {
        let scan = if with_scan {
            let mut sub = std::collections::BTreeMap::new();
            for (k, _) in crate::cli::color::AXES {
                sub.insert(k.to_string(), 70i64);
            }
            Some(ScanReportDetail {
                id: "s".into(),
                github_url: None,
                slug: "a--b--mcp-server-x".into(),
                display_name: "X".into(),
                aggregate_score: score,
                tier,
                sub_scores: sub,
                findings: if with_findings {
                    vec![finding(Severity::Critical), finding(Severity::Low)]
                } else {
                    vec![]
                },
                scanned_at: None,
                rubric_version: None,
                engine_version: None,
                component_path: None,
                scan_run_id: None,
            })
        } else {
            None
        };
        ItemDetailResponse {
            item: item("a--b--mcp-server-x", "mcp_server", "X", Some(score)),
            latest_scan: scan,
        }
    }

    fn draw(state: &AppState, color: bool, tick: u64) {
        let backend = TestBackend::new(120, 40);
        let mut term = Terminal::new(backend).unwrap();
        term.draw(|f| render(f, state, color, tick)).unwrap();
    }

    fn loaded_state() -> AppState {
        let mut s = AppState::new(String::new(), Facets::default(), None, 50);
        let seq = s.next_list_seq();
        s.apply_results(
            seq,
            envelope(
                vec![
                    item("a--b--mcp-server-x", "mcp_server", "Redis MCP", Some(91)),
                    item("a--b--skill-y", "skill", "PDF Skill", Some(55)),
                    item("a--b--hook-z", "hook", "Unscored Hook", None),
                ],
                120,
            ),
        );
        s
    }

    #[test]
    fn renders_empty_loading_state() {
        let mut s = AppState::new(String::new(), Facets::default(), None, 50);
        s.loading.list = true;
        draw(&s, true, 0);
        draw(&s, false, 3);
    }

    #[test]
    fn renders_no_match_and_error_states() {
        let s = AppState::new("zzz".into(), Facets::default(), None, 50);
        draw(&s, true, 0);
        let mut e = AppState::new("zzz".into(), Facets::default(), None, 50);
        e.error = Some("network error".into());
        draw(&e, false, 0);
    }

    #[test]
    fn renders_loaded_list_color_and_mono() {
        let mut s = loaded_state();
        s.toggle_mark(); // mark the highlighted row
        draw(&s, true, 1);
        draw(&s, false, 2);
    }

    #[test]
    fn renders_filters_focus_with_facets_on() {
        let mut s = loaded_state();
        s.set_focus(crate::tui::search::state::Focus::Filters);
        s.toggle_kind("skill");
        s.toggle_scan_tier("green");
        s.toggle_agent("claude-code");
        s.facets.min_score = 40;
        s.toggle_low_quality();
        // Walk the facet cursor onto the score row, then the low-quality row.
        s.facet_cursor = crate::tui::search::state::FACET_COUNT - 2;
        draw(&s, true, 0);
        s.facet_cursor = crate::tui::search::state::FACET_COUNT - 1;
        draw(&s, false, 0);
    }

    #[test]
    fn renders_preview_loaded_with_findings() {
        let mut s = loaded_state();
        let pseq = s.next_preview_seq();
        s.apply_preview(
            pseq,
            "a--b--mcp-server-x".into(),
            detail(91, Tier::Green, true, true),
        );
        draw(&s, true, 0);
        draw(&s, false, 0);
    }

    #[test]
    fn renders_preview_no_findings_and_unscanned() {
        // No-findings scan.
        let mut s = loaded_state();
        let pseq = s.next_preview_seq();
        s.apply_preview(
            pseq,
            "a--b--mcp-server-x".into(),
            detail(95, Tier::Green, false, true),
        );
        draw(&s, true, 0);
        // Unscanned (no latest_scan) preview for a different highlighted row.
        let mut u = loaded_state();
        u.move_highlight(2); // the hook (no score)
        let pseq = u.next_preview_seq();
        u.apply_preview(
            pseq,
            "a--b--hook-z".into(),
            detail(0, Tier::Unscoped, false, false),
        );
        draw(&u, true, 0);
    }

    #[test]
    fn renders_preview_loading_state() {
        let mut s = loaded_state();
        s.loading.preview = true;
        draw(&s, true, 0);
    }

    #[test]
    fn flat_index_round_trips_facets() {
        for i in 0..FACET_COUNT {
            assert_eq!(flat_index(facet_at(i)), i);
        }
    }
}
