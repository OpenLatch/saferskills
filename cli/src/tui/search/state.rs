//! Pure state core for the `search` TUI. Holds the query + cursor, the facet
//! filters, the loaded candidate pool, the locally-ranked view, the marked set,
//! the loading flags, and the preview cache. Every transition here is pure
//! (no I/O, no terminal) so the bulk of the command is unit-tested without a
//! TTY; the ratatui draw + event loop stay a thin shell over this.

use std::collections::BTreeMap;

use crate::api::dto::{CatalogItemSummary, CatalogListEnvelope, ItemDetailResponse};
use crate::api::CatalogQuery;

use super::rank;

/// The kinds a user can toggle, in sidebar order.
pub const KINDS: [&str; 5] = ["skill", "mcp_server", "hook", "plugin", "rules"];
/// The scan tiers a user can toggle, in sidebar order.
pub const TIERS: [&str; 4] = ["green", "yellow", "orange", "red"];
/// The agent ids a user can toggle, in sidebar order (the backend `ALL_AGENTS`).
pub const AGENTS: [&str; 8] = [
    "claude-code",
    "cursor",
    "codex",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "openclaw",
];

/// Score stepper increments.
const STEP: i16 = 5;
const COARSE_STEP: i16 = 10;

/// Which pane has keyboard focus. Typing always edits the query when focus is
/// `Query`; facet navigation/toggles happen under `Filters` (Tab switches). This
/// avoids the digit-vs-query-text conflict a hotkey scheme would create.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    Query,
    Filters,
}

/// One navigable item in the flattened facet sidebar (Filters focus).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FacetItem {
    Kind(usize),
    Tier(usize),
    Agent(usize),
    Score,
    LowQuality,
}

/// Total navigable facet items (the sidebar order: kinds, tiers, agents, score,
/// low-quality).
pub const FACET_COUNT: usize = KINDS.len() + TIERS.len() + AGENTS.len() + 2;

/// Resolve the flattened facet index to its [`FacetItem`].
pub fn facet_at(idx: usize) -> FacetItem {
    let (nk, nt, na) = (KINDS.len(), TIERS.len(), AGENTS.len());
    if idx < nk {
        FacetItem::Kind(idx)
    } else if idx < nk + nt {
        FacetItem::Tier(idx - nk)
    } else if idx < nk + nt + na {
        FacetItem::Agent(idx - nk - nt)
    } else if idx == nk + nt + na {
        FacetItem::Score
    } else {
        FacetItem::LowQuality
    }
}

/// The two in-TUI loading states (install progress is NOT here — it runs after
/// the TUI tears down, as normal CLI output).
#[derive(Debug, Default, Clone, Copy)]
pub struct Loading {
    /// A trending/search list fetch is in flight (spinner in the query line;
    /// the stale list stays visible — stale-while-revalidate).
    pub list: bool,
    /// A preview (`get_item`) fetch is in flight for the highlighted row.
    pub preview: bool,
}

/// The active facet filters.
#[derive(Debug, Default, Clone)]
pub struct Facets {
    pub kinds: Vec<String>,
    pub agents: Vec<String>,
    pub scan_tiers: Vec<String>,
    /// Minimum aggregate score (0–100). `0` = no filter.
    pub min_score: u8,
    /// Include low/empty quality_tier items.
    pub show_low_quality: bool,
}

/// The whole interactive state.
#[derive(Debug)]
pub struct AppState {
    /// The query text (raw, untrimmed).
    pub query: String,
    /// Cursor position as a char index into `query`.
    pub cursor: usize,
    pub facets: Facets,
    /// Server sort key (`None` → server default `most_installed`).
    pub sort: Option<String>,
    /// Page size for each fetch.
    pub limit: u32,
    /// The loaded candidate pool (server order).
    pub candidates: Vec<CatalogItemSummary>,
    /// Indices into `candidates`, locally fuzzy-ranked against `query`.
    pub ranked: Vec<usize>,
    /// Highlight position, an index into `ranked`.
    pub highlight: usize,
    /// Marked-for-install set, keyed by slug so it survives query/facet changes.
    pub marked: BTreeMap<String, CatalogItemSummary>,
    pub loading: Loading,
    /// Total catalog matches server-side (for the "showing top N" hint).
    pub total_count: i64,
    /// The seq of the most-recently dispatched list fetch (staleness guard).
    pub dispatched_list_seq: u64,
    /// The seq of the most-recently dispatched preview fetch.
    pub dispatched_preview_seq: u64,
    /// Preview details by slug (debounced + cached).
    pub preview_cache: BTreeMap<String, ItemDetailResponse>,
    /// The last fetch error to surface (cleared on the next successful apply).
    pub error: Option<String>,
    /// Set when Esc/Ctrl-C cancels.
    pub cancelled: bool,
    /// Set when Enter accepts the marked set for install.
    pub accepted: bool,
    /// Which pane has keyboard focus.
    pub focus: Focus,
    /// Cursor into the flattened facet list (used under `Focus::Filters`).
    pub facet_cursor: usize,
}

impl AppState {
    /// Build the initial state from the seed query + facets + sort/limit.
    pub fn new(query: String, facets: Facets, sort: Option<String>, limit: u32) -> Self {
        let cursor = query.chars().count();
        Self {
            query,
            cursor,
            facets,
            sort,
            limit,
            candidates: Vec::new(),
            ranked: Vec::new(),
            highlight: 0,
            marked: BTreeMap::new(),
            loading: Loading::default(),
            total_count: 0,
            dispatched_list_seq: 0,
            dispatched_preview_seq: 0,
            preview_cache: BTreeMap::new(),
            error: None,
            cancelled: false,
            accepted: false,
            focus: Focus::Query,
            facet_cursor: 0,
        }
    }

    // ─── focus + facet navigation (pure) ───────────────────────────────────────

    /// Toggle focus between the query and the filter sidebar.
    pub fn toggle_focus(&mut self) {
        self.focus = match self.focus {
            Focus::Query => Focus::Filters,
            Focus::Filters => Focus::Query,
        };
    }

    /// Set focus explicitly.
    pub fn set_focus(&mut self, focus: Focus) {
        self.focus = focus;
    }

    /// Move the facet cursor by `delta`, clamped to the facet list.
    pub fn move_facet(&mut self, delta: i32) {
        let max = FACET_COUNT as i32 - 1;
        let next = (self.facet_cursor as i32 + delta).clamp(0, max);
        self.facet_cursor = next as usize;
    }

    /// The facet item currently under the cursor.
    pub fn current_facet(&self) -> FacetItem {
        facet_at(self.facet_cursor.min(FACET_COUNT - 1))
    }

    /// Toggle the facet under the cursor. Score is a no-op here (adjusted via
    /// [`AppState::bump_score`]). Returns whether a refetch is warranted (every
    /// toggle except Score → true).
    pub fn toggle_current_facet(&mut self) -> bool {
        match self.current_facet() {
            FacetItem::Kind(i) => {
                let k = KINDS[i];
                self.toggle_kind(k);
                true
            }
            FacetItem::Tier(i) => {
                let t = TIERS[i];
                self.toggle_scan_tier(t);
                true
            }
            FacetItem::Agent(i) => {
                let a = AGENTS[i];
                self.toggle_agent(a);
                true
            }
            FacetItem::LowQuality => {
                self.toggle_low_quality();
                true
            }
            FacetItem::Score => false,
        }
    }

    // ─── query lowering ──────────────────────────────────────────────────────

    /// Build the API query from the current query text + facets + sort/limit.
    pub fn to_query(&self) -> CatalogQuery {
        CatalogQuery {
            q: Some(self.query.clone()),
            kinds: self.facets.kinds.clone(),
            agents: self.facets.agents.clone(),
            scan_tiers: self.facets.scan_tiers.clone(),
            score_min: Some(self.facets.min_score),
            sort: self.sort.clone(),
            limit: self.limit,
            show_low_quality: self.facets.show_low_quality,
        }
    }

    // ─── text editing (pure) ───────────────────────────────────────────────────

    /// Insert a char at the cursor. Returns true (query changed).
    pub fn insert_char(&mut self, ch: char) -> bool {
        let mut chars: Vec<char> = self.query.chars().collect();
        let at = self.cursor.min(chars.len());
        chars.insert(at, ch);
        self.query = chars.into_iter().collect();
        self.cursor = at + 1;
        true
    }

    /// Delete the char before the cursor. Returns whether the query changed.
    pub fn backspace(&mut self) -> bool {
        if self.cursor == 0 {
            return false;
        }
        let mut chars: Vec<char> = self.query.chars().collect();
        let at = self.cursor - 1;
        chars.remove(at);
        self.query = chars.into_iter().collect();
        self.cursor = at;
        true
    }

    /// Move the cursor one char left.
    pub fn cursor_left(&mut self) {
        self.cursor = self.cursor.saturating_sub(1);
    }

    /// Move the cursor one char right (bounded by the query length).
    pub fn cursor_right(&mut self) {
        let len = self.query.chars().count();
        self.cursor = (self.cursor + 1).min(len);
    }

    // ─── facet toggles (pure) ──────────────────────────────────────────────────

    /// Toggle a kind in the filter set.
    pub fn toggle_kind(&mut self, kind: &str) {
        toggle(&mut self.facets.kinds, kind);
    }

    /// Toggle an agent in the filter set.
    pub fn toggle_agent(&mut self, agent: &str) {
        toggle(&mut self.facets.agents, agent);
    }

    /// Toggle a scan tier in the filter set.
    pub fn toggle_scan_tier(&mut self, tier: &str) {
        toggle(&mut self.facets.scan_tiers, tier);
    }

    /// Toggle the show-low-quality flag.
    pub fn toggle_low_quality(&mut self) {
        self.facets.show_low_quality = !self.facets.show_low_quality;
    }

    /// Step the min-score filter, clamped to 0–100. `coarse` uses the ±10 step.
    pub fn bump_score(&mut self, up: bool, coarse: bool) {
        let step = if coarse { COARSE_STEP } else { STEP };
        let delta = if up { step } else { -step };
        let next = (self.facets.min_score as i16 + delta).clamp(0, 100);
        self.facets.min_score = next as u8;
    }

    // ─── dispatch / staleness (pure) ───────────────────────────────────────────

    /// Claim the next list-fetch seq + mark the list as loading.
    pub fn next_list_seq(&mut self) -> u64 {
        self.dispatched_list_seq += 1;
        self.loading.list = true;
        self.dispatched_list_seq
    }

    /// Claim the next preview-fetch seq + mark the preview as loading.
    pub fn next_preview_seq(&mut self) -> u64 {
        self.dispatched_preview_seq += 1;
        self.loading.preview = true;
        self.dispatched_preview_seq
    }

    /// Whether a list response tagged `seq` is stale (superseded).
    pub fn is_stale_list(&self, seq: u64) -> bool {
        seq < self.dispatched_list_seq
    }

    /// Apply a list response. Drops stale (out-of-order) responses. On apply it
    /// replaces the pool, re-ranks, clamps the highlight, and clears the loading
    /// flag. Returns whether it was applied.
    pub fn apply_results(&mut self, seq: u64, env: CatalogListEnvelope) -> bool {
        if self.is_stale_list(seq) {
            return false;
        }
        self.loading.list = false;
        self.error = None;
        self.total_count = env.total_count;
        self.candidates = env.data;
        self.re_rank();
        true
    }

    /// Record a list-fetch error for the latest dispatch (stale errors ignored).
    pub fn apply_list_error(&mut self, seq: u64, message: String) -> bool {
        if self.is_stale_list(seq) {
            return false;
        }
        self.loading.list = false;
        self.error = Some(message);
        true
    }

    /// Apply a preview response (dropping stale ones) into the cache.
    pub fn apply_preview(&mut self, seq: u64, slug: String, detail: ItemDetailResponse) -> bool {
        if seq < self.dispatched_preview_seq {
            return false;
        }
        self.loading.preview = false;
        self.preview_cache.insert(slug, detail);
        true
    }

    /// Clear the preview loading flag on a failed preview fetch.
    pub fn clear_preview_loading(&mut self, seq: u64) {
        if seq >= self.dispatched_preview_seq {
            self.loading.preview = false;
        }
    }

    // ─── ranking + selection (pure) ────────────────────────────────────────────

    /// Re-rank the candidate pool locally against the query + clamp the highlight.
    pub fn re_rank(&mut self) {
        let haystacks: Vec<String> = self.candidates.iter().map(haystack).collect();
        self.ranked = rank::rank(&self.query, &haystacks);
        self.clamp_highlight();
    }

    fn clamp_highlight(&mut self) {
        if self.ranked.is_empty() {
            self.highlight = 0;
        } else if self.highlight >= self.ranked.len() {
            self.highlight = self.ranked.len() - 1;
        }
    }

    /// Move the highlight by `delta` rows, clamped to the visible list.
    pub fn move_highlight(&mut self, delta: i32) {
        if self.ranked.is_empty() {
            self.highlight = 0;
            return;
        }
        let max = self.ranked.len() as i32 - 1;
        let next = (self.highlight as i32 + delta).clamp(0, max);
        self.highlight = next as usize;
    }

    /// The currently highlighted catalog item, if any.
    pub fn highlighted(&self) -> Option<&CatalogItemSummary> {
        let idx = *self.ranked.get(self.highlight)?;
        self.candidates.get(idx)
    }

    /// Toggle the marked state of the highlighted item (no-op if none).
    pub fn toggle_mark(&mut self) {
        let Some(item) = self.highlighted().cloned() else {
            return;
        };
        if self.marked.remove(&item.slug).is_none() {
            self.marked.insert(item.slug.clone(), item);
        }
    }

    /// Whether a slug is currently marked.
    pub fn is_marked(&self, slug: &str) -> bool {
        self.marked.contains_key(slug)
    }

    /// The marked items in slug order (the install selection).
    pub fn marked_items(&self) -> Vec<CatalogItemSummary> {
        self.marked.values().cloned().collect()
    }

    /// The number of loaded (visible) rows vs total matches — drives the hint.
    pub fn is_truncated(&self) -> bool {
        self.total_count > self.candidates.len() as i64
    }

    /// The slug needing a preview fetch: the highlighted row, when not cached and
    /// not already the in-flight target. `None` when nothing to fetch.
    pub fn preview_target(&self) -> Option<String> {
        let slug = &self.highlighted()?.slug;
        if self.preview_cache.contains_key(slug) {
            return None;
        }
        Some(slug.clone())
    }

    /// The cached preview for the highlighted row, if loaded.
    pub fn current_preview(&self) -> Option<&ItemDetailResponse> {
        let slug = &self.highlighted()?.slug;
        self.preview_cache.get(slug)
    }

    // ─── terminal transitions ──────────────────────────────────────────────────

    /// Accept the current selection for install. If nothing is explicitly marked
    /// but a row is highlighted, the highlighted row becomes the selection.
    pub fn accept(&mut self) {
        if self.marked.is_empty() {
            if let Some(item) = self.highlighted().cloned() {
                self.marked.insert(item.slug.clone(), item);
            }
        }
        self.accepted = true;
    }

    /// Cancel the search (Esc / Ctrl-C).
    pub fn cancel(&mut self) {
        self.cancelled = true;
    }
}

/// The fuzzy-match haystack for an item: display name + slug (so both a typed
/// pretty name and the slug tail match).
fn haystack(item: &CatalogItemSummary) -> String {
    format!("{} {}", item.display_name, item.slug)
}

/// Toggle a value in a Vec acting as a set (insert if absent, remove if present).
fn toggle(set: &mut Vec<String>, value: &str) {
    if let Some(pos) = set.iter().position(|v| v == value) {
        set.remove(pos);
    } else {
        set.push(value.to_string());
    }
}

/// Whether the CLI can install a capability of this kind today (skills + MCP
/// servers only). Hooks/plugins/rules are discoverable but install-skipped.
pub fn is_installable_kind(kind: &str) -> bool {
    matches!(kind, "skill" | "mcp_server")
}

/// Split a selection into (installable, skipped) by kind — the install loop
/// installs the first set and prints a skip-notice + report link for the rest.
pub fn installable_split(
    items: &[CatalogItemSummary],
) -> (Vec<CatalogItemSummary>, Vec<CatalogItemSummary>) {
    items
        .iter()
        .cloned()
        .partition(|i| is_installable_kind(&i.kind))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::Tier;

    fn item(slug: &str, kind: &str, name: &str) -> CatalogItemSummary {
        CatalogItemSummary {
            id: slug.into(),
            slug: slug.into(),
            kind: kind.into(),
            display_name: name.into(),
            description: None,
            github_url: None,
            github_org: None,
            github_repo: None,
            source_kind: None,
            popularity_tier: "emerging".into(),
            popularity_score: 0,
            latest_scan_score: Some(80),
            latest_scan_tier: Some(Tier::Green),
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

    fn state() -> AppState {
        AppState::new(String::new(), Facets::default(), None, 50)
    }

    #[test]
    fn to_query_lowers_facets() {
        let mut s = state();
        s.query = "redis".into();
        s.facets.kinds = vec!["mcp_server".into()];
        s.facets.min_score = 70;
        let q = s.to_query();
        assert_eq!(q.q.as_deref(), Some("redis"));
        assert_eq!(q.kinds, vec!["mcp_server".to_string()]);
        assert_eq!(q.score_min, Some(70));
        assert_eq!(q.limit, 50);
    }

    #[test]
    fn text_editing_inserts_and_backspaces() {
        let mut s = state();
        assert!(s.insert_char('r'));
        assert!(s.insert_char('d'));
        s.cursor_left();
        s.insert_char('e'); // r e d (e inserted before d)
        assert_eq!(s.query, "red");
        assert!(s.backspace());
        assert_eq!(s.query, "rd");
        // Backspace at start is a no-op.
        s.cursor = 0;
        assert!(!s.backspace());
    }

    #[test]
    fn facet_toggles_are_idempotent_pairs() {
        let mut s = state();
        s.toggle_kind("skill");
        assert_eq!(s.facets.kinds, vec!["skill".to_string()]);
        s.toggle_kind("skill");
        assert!(s.facets.kinds.is_empty());
        s.toggle_agent("codex");
        assert_eq!(s.facets.agents, vec!["codex".to_string()]);
        s.toggle_scan_tier("green");
        assert_eq!(s.facets.scan_tiers, vec!["green".to_string()]);
        assert!(!s.facets.show_low_quality);
        s.toggle_low_quality();
        assert!(s.facets.show_low_quality);
    }

    #[test]
    fn score_stepper_clamps() {
        let mut s = state();
        s.bump_score(false, false); // 0 - 5 → clamp 0
        assert_eq!(s.facets.min_score, 0);
        for _ in 0..3 {
            s.bump_score(true, false);
        }
        assert_eq!(s.facets.min_score, 15);
        s.bump_score(true, true); // +10
        assert_eq!(s.facets.min_score, 25);
        for _ in 0..20 {
            s.bump_score(true, true);
        }
        assert_eq!(s.facets.min_score, 100); // clamps at 100
    }

    #[test]
    fn stale_list_response_is_dropped() {
        let mut s = state();
        let seq1 = s.next_list_seq(); // 1
        let seq2 = s.next_list_seq(); // 2, supersedes 1
                                      // seq1 is now stale.
        assert!(!s.apply_results(seq1, envelope(vec![item("a--b--skill-x", "skill", "X")], 1)));
        assert!(s.candidates.is_empty());
        // seq2 applies.
        assert!(s.apply_results(seq2, envelope(vec![item("a--b--skill-y", "skill", "Y")], 1)));
        assert_eq!(s.candidates.len(), 1);
        assert!(!s.loading.list);
    }

    #[test]
    fn ranking_and_marking_survive_query_change() {
        let mut s = state();
        let seq = s.next_list_seq();
        s.apply_results(
            seq,
            envelope(
                vec![
                    item("a--b--skill-redis", "skill", "Redis Helper"),
                    item("a--b--mcp-server-pg", "mcp_server", "Postgres"),
                ],
                2,
            ),
        );
        // Highlight + mark the first row.
        assert_eq!(s.highlighted().unwrap().slug, "a--b--skill-redis");
        s.toggle_mark();
        assert!(s.is_marked("a--b--skill-redis"));
        // Narrow the query so the marked row leaves the visible pool.
        s.query = "postgres".into();
        s.re_rank();
        assert_eq!(s.highlighted().unwrap().slug, "a--b--mcp-server-pg");
        // The mark persists even though the row is no longer visible.
        assert!(s.is_marked("a--b--skill-redis"));
        assert_eq!(s.marked_items().len(), 1);
    }

    #[test]
    fn move_highlight_clamps_within_visible() {
        let mut s = state();
        let seq = s.next_list_seq();
        s.apply_results(
            seq,
            envelope(
                vec![
                    item("a--b--skill-1", "skill", "One"),
                    item("a--b--skill-2", "skill", "Two"),
                ],
                2,
            ),
        );
        s.move_highlight(-1);
        assert_eq!(s.highlight, 0);
        s.move_highlight(5);
        assert_eq!(s.highlight, 1);
    }

    #[test]
    fn installable_split_partitions_by_kind() {
        let items = vec![
            item("a--b--skill-x", "skill", "X"),
            item("a--b--mcp-server-y", "mcp_server", "Y"),
            item("a--b--hook-z", "hook", "Z"),
            item("a--b--plugin-w", "plugin", "W"),
            item("a--b--rules-v", "rules", "V"),
        ];
        let (inst, skip) = installable_split(&items);
        assert_eq!(inst.len(), 2);
        assert_eq!(skip.len(), 3);
        assert!(inst.iter().all(|i| is_installable_kind(&i.kind)));
        assert!(skip.iter().all(|i| !is_installable_kind(&i.kind)));
    }

    #[test]
    fn preview_target_skips_cached_and_applies_fresh() {
        let mut s = state();
        let seq = s.next_list_seq();
        s.apply_results(seq, envelope(vec![item("a--b--skill-x", "skill", "X")], 1));
        // Highlighted, uncached → a fetch target.
        assert_eq!(s.preview_target().as_deref(), Some("a--b--skill-x"));
        let pseq = s.next_preview_seq();
        let detail = ItemDetailResponse {
            item: item("a--b--skill-x", "skill", "X"),
            latest_scan: None,
        };
        assert!(s.apply_preview(pseq, "a--b--skill-x".into(), detail));
        // Now cached → no fetch target, and the preview resolves.
        assert!(s.preview_target().is_none());
        assert!(s.current_preview().is_some());
        assert!(!s.loading.preview);
    }

    #[test]
    fn accept_marks_highlighted_when_empty() {
        let mut s = state();
        let seq = s.next_list_seq();
        s.apply_results(seq, envelope(vec![item("a--b--skill-x", "skill", "X")], 1));
        s.accept();
        assert!(s.accepted);
        assert_eq!(s.marked_items().len(), 1);
    }

    #[test]
    fn is_truncated_when_total_exceeds_loaded() {
        let mut s = state();
        let seq = s.next_list_seq();
        s.apply_results(
            seq,
            envelope(vec![item("a--b--skill-x", "skill", "X")], 120),
        );
        assert!(s.is_truncated());
    }

    #[test]
    fn focus_toggles_between_query_and_filters() {
        let mut s = state();
        assert_eq!(s.focus, Focus::Query);
        s.toggle_focus();
        assert_eq!(s.focus, Focus::Filters);
        s.toggle_focus();
        assert_eq!(s.focus, Focus::Query);
    }

    #[test]
    fn facet_cursor_navigates_and_resolves_items() {
        let mut s = state();
        assert_eq!(s.current_facet(), FacetItem::Kind(0));
        s.move_facet(-1); // clamps at 0
        assert_eq!(s.facet_cursor, 0);
        // Step onto the first tier (after the 5 kinds).
        s.move_facet(KINDS.len() as i32);
        assert_eq!(s.current_facet(), FacetItem::Tier(0));
        // Jump to the very end → LowQuality.
        s.move_facet(FACET_COUNT as i32);
        assert_eq!(s.current_facet(), FacetItem::LowQuality);
    }

    #[test]
    fn toggle_current_facet_drives_each_group() {
        let mut s = state();
        // Kind(0) = skill.
        assert!(s.toggle_current_facet());
        assert_eq!(s.facets.kinds, vec!["skill".to_string()]);
        // Move to Score → toggle is a no-op (false, adjusted via bump_score).
        s.facet_cursor = KINDS.len() + TIERS.len() + AGENTS.len();
        assert_eq!(s.current_facet(), FacetItem::Score);
        assert!(!s.toggle_current_facet());
        // LowQuality flips.
        s.move_facet(1);
        assert!(s.toggle_current_facet());
        assert!(s.facets.show_low_quality);
    }

    #[test]
    fn facet_at_maps_index_ranges() {
        assert_eq!(facet_at(0), FacetItem::Kind(0));
        assert_eq!(facet_at(KINDS.len()), FacetItem::Tier(0));
        assert_eq!(facet_at(KINDS.len() + TIERS.len()), FacetItem::Agent(0));
        assert_eq!(
            facet_at(KINDS.len() + TIERS.len() + AGENTS.len()),
            FacetItem::Score
        );
        assert_eq!(facet_at(FACET_COUNT - 1), FacetItem::LowQuality);
    }
}
