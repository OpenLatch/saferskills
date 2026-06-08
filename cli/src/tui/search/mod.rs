//! The `search` TUI runtime: the async `tokio::select!` loop, channels, debounce,
//! and the nucleo-ranked candidate pool. The heavy logic lives in the pure
//! [`state`] core; this module is the thin shell that wires events → state →
//! render and the debounced/cancellable fetches.
//!
//! Concurrency: one tokio runtime (built in `main.rs`), selecting over an async
//! crossterm `EventStream` (keys), an `mpsc` of tagged API responses (stale ones
//! dropped by monotonic seq), and a ~30 fps interval (spinner + debounce poll).

pub mod rank;
pub mod state;
pub mod view;

use std::time::{Duration, Instant};

use crossterm::event::{Event, EventStream, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use futures_util::StreamExt;
use tokio::sync::mpsc;

use crate::api::dto::{CatalogItemSummary, CatalogListEnvelope, ItemDetailResponse};
use crate::api::Api;
use crate::core::error::{SsError, ERR_BUG};

use self::state::{AppState, FacetItem, Facets, Focus};
use crate::tui::terminal::TerminalGuard;

/// Debounce windows: re-rank is instant; the server refetch fires after a quiet
/// gap; the preview fetch debounces while scrolling.
const LIST_DEBOUNCE: Duration = Duration::from_millis(180);
const PREVIEW_DEBOUNCE: Duration = Duration::from_millis(180);
/// Render/animation cadence (~30 fps).
const TICK: Duration = Duration::from_millis(33);

/// A tagged async API response funneled back into the loop. The result payloads
/// are boxed — the DTOs are large, and boxing keeps the channel message small
/// (and the two variants size-balanced).
enum ApiMsg {
    List {
        seq: u64,
        result: Box<Result<CatalogListEnvelope, SsError>>,
    },
    Preview {
        seq: u64,
        slug: String,
        result: Box<Result<ItemDetailResponse, SsError>>,
    },
}

/// What a handled key implies for fetching.
#[derive(Default, Debug, PartialEq, Eq)]
struct KeyOutcome {
    /// The query changed → debounce a list refetch.
    debounce_list: bool,
    /// A facet changed → refetch immediately.
    refetch_now: bool,
    /// The highlight changed → debounce a preview fetch.
    debounce_preview: bool,
}

/// Run the interactive search TUI. Returns the marked items to install (empty =
/// cancelled). The terminal is fully restored before this returns (the RAII
/// guard is dropped here), so the caller's install output is plain CLI output.
pub async fn run(
    api: Api,
    seed_query: String,
    seed_facets: Facets,
    sort: Option<String>,
    limit: u32,
    color: bool,
) -> Result<Vec<CatalogItemSummary>, SsError> {
    let mut guard = TerminalGuard::enter()?;
    let outcome = event_loop(
        &mut guard,
        &api,
        seed_query,
        seed_facets,
        sort,
        limit,
        color,
    )
    .await;
    // Explicit drop → terminal restored before the caller prints anything.
    drop(guard);
    outcome
}

#[allow(clippy::too_many_arguments)]
async fn event_loop(
    guard: &mut TerminalGuard,
    api: &Api,
    seed_query: String,
    seed_facets: Facets,
    sort: Option<String>,
    limit: u32,
    color: bool,
) -> Result<Vec<CatalogItemSummary>, SsError> {
    let mut st = AppState::new(seed_query, seed_facets, sort, limit);
    let (tx, mut rx) = mpsc::channel::<ApiMsg>(32);
    let mut events = EventStream::new();
    let mut ticker = tokio::time::interval(TICK);
    let mut tick: u64 = 0;
    let mut pending_list: Option<Instant> = None;
    let mut pending_preview: Option<Instant> = None;

    // Initial trending/seed fetch.
    dispatch_list(api, &mut st, &tx);

    loop {
        guard
            .terminal()
            .draw(|f| view::render(f, &st, color, tick))
            .map_err(draw_err)?;

        tokio::select! {
            maybe_event = events.next() => match maybe_event {
                Some(Ok(Event::Key(key))) => {
                    if key.kind == KeyEventKind::Release {
                        continue; // Windows emits release events; ignore them.
                    }
                    let out = handle_key(&mut st, key);
                    if st.accepted || st.cancelled {
                        break;
                    }
                    apply_outcome(api, &mut st, &tx, out, &mut pending_list, &mut pending_preview);
                }
                Some(Ok(_)) => {} // resize / mouse → redrawn next iteration
                Some(Err(_)) => {}
                None => break,
            },
            Some(msg) = rx.recv() => {
                apply_msg(msg, &mut st);
                // A fresh list can change the highlighted row → maybe preview it.
                schedule_preview(&st, &mut pending_preview);
            }
            _ = ticker.tick() => {
                tick = tick.wrapping_add(1);
                let now = Instant::now();
                if pending_list.is_some_and(|d| now >= d) {
                    pending_list = None;
                    dispatch_list(api, &mut st, &tx);
                }
                if pending_preview.is_some_and(|d| now >= d) {
                    pending_preview = None;
                    dispatch_preview(api, &mut st, &tx);
                }
            }
        }
    }

    if st.accepted {
        Ok(st.marked_items())
    } else {
        Ok(Vec::new())
    }
}

/// Apply a key outcome: refetch immediately on a facet change, else debounce.
fn apply_outcome(
    api: &Api,
    st: &mut AppState,
    tx: &mpsc::Sender<ApiMsg>,
    out: KeyOutcome,
    pending_list: &mut Option<Instant>,
    pending_preview: &mut Option<Instant>,
) {
    if out.refetch_now {
        dispatch_list(api, st, tx);
    } else if out.debounce_list {
        *pending_list = Some(Instant::now() + LIST_DEBOUNCE);
    }
    if out.debounce_preview {
        schedule_preview(st, pending_preview);
    }
}

/// Schedule a debounced preview fetch when the highlighted row needs one.
fn schedule_preview(st: &AppState, pending_preview: &mut Option<Instant>) {
    if st.preview_target().is_some() {
        *pending_preview = Some(Instant::now() + PREVIEW_DEBOUNCE);
    }
}

/// Fire a list fetch (claims a seq, spawns the request, funnels the result back).
fn dispatch_list(api: &Api, st: &mut AppState, tx: &mpsc::Sender<ApiMsg>) {
    let seq = st.next_list_seq();
    let query = st.to_query();
    let api = api.clone();
    let tx = tx.clone();
    tokio::spawn(async move {
        let result = Box::new(api.list_items(&query).await);
        let _ = tx.send(ApiMsg::List { seq, result }).await;
    });
}

/// Fire a preview fetch for the highlighted, uncached row (no-op otherwise).
fn dispatch_preview(api: &Api, st: &mut AppState, tx: &mpsc::Sender<ApiMsg>) {
    let Some(slug) = st.preview_target() else {
        return;
    };
    let seq = st.next_preview_seq();
    let api = api.clone();
    let tx = tx.clone();
    tokio::spawn(async move {
        let result = Box::new(api.get_item(&slug).await);
        let _ = tx.send(ApiMsg::Preview { seq, slug, result }).await;
    });
}

fn apply_msg(msg: ApiMsg, st: &mut AppState) {
    match msg {
        ApiMsg::List { seq, result } => match *result {
            Ok(env) => {
                st.apply_results(seq, env);
            }
            Err(e) => {
                st.apply_list_error(seq, e.message);
            }
        },
        ApiMsg::Preview { seq, slug, result } => match *result {
            Ok(detail) => {
                st.apply_preview(seq, slug, detail);
            }
            Err(_) => st.clear_preview_loading(seq),
        },
    }
}

/// Pure key→state transition (returns the fetch implication). Testable without a
/// terminal: it takes a constructed [`KeyEvent`] and mutates the state.
fn handle_key(st: &mut AppState, key: KeyEvent) -> KeyOutcome {
    let mut out = KeyOutcome::default();
    let code = key.code;
    let mods = key.modifiers;
    let ctrl = mods.contains(KeyModifiers::CONTROL);

    // Ctrl-C cancels from anywhere.
    if ctrl && matches!(code, KeyCode::Char('c')) {
        st.cancel();
        return out;
    }
    // Ctrl-F toggles the filter sidebar focus from anywhere.
    if ctrl && matches!(code, KeyCode::Char('f')) {
        st.toggle_focus();
        return out;
    }

    match st.focus {
        Focus::Query => match code {
            KeyCode::Enter => st.accept(),
            KeyCode::Esc => st.cancel(),
            KeyCode::Tab => st.toggle_mark(),
            KeyCode::Up => {
                st.move_highlight(-1);
                out.debounce_preview = true;
            }
            KeyCode::Down => {
                st.move_highlight(1);
                out.debounce_preview = true;
            }
            KeyCode::Backspace => {
                if st.backspace() {
                    st.re_rank();
                    out.debounce_list = true;
                    out.debounce_preview = true;
                }
            }
            KeyCode::Char(c) if !ctrl => {
                st.insert_char(c);
                st.re_rank();
                out.debounce_list = true;
                out.debounce_preview = true;
            }
            _ => {}
        },
        Focus::Filters => match code {
            KeyCode::Tab | KeyCode::Esc => st.set_focus(Focus::Query),
            KeyCode::Up => st.move_facet(-1),
            KeyCode::Down => st.move_facet(1),
            KeyCode::Left if st.current_facet() == FacetItem::Score => {
                st.bump_score(false, mods.contains(KeyModifiers::SHIFT));
                out.refetch_now = true;
            }
            KeyCode::Right if st.current_facet() == FacetItem::Score => {
                st.bump_score(true, mods.contains(KeyModifiers::SHIFT));
                out.refetch_now = true;
            }
            KeyCode::Char(' ') | KeyCode::Enter => {
                if st.toggle_current_facet() {
                    out.refetch_now = true;
                }
            }
            // Typing a letter in Filters jumps back to the query and inserts it.
            KeyCode::Char(c) if !ctrl => {
                st.set_focus(Focus::Query);
                st.insert_char(c);
                st.re_rank();
                out.debounce_list = true;
                out.debounce_preview = true;
            }
            _ => {}
        },
    }
    out
}

fn draw_err(e: std::io::Error) -> SsError {
    SsError::new(ERR_BUG, format!("Terminal render failed: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    fn ctrl(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::CONTROL)
    }

    fn state() -> AppState {
        AppState::new(String::new(), Facets::default(), None, 50)
    }

    fn one_item_env() -> CatalogListEnvelope {
        CatalogListEnvelope {
            data: vec![crate::api::dto::CatalogItemSummary {
                id: "i".into(),
                slug: "a--b--skill-x".into(),
                kind: "skill".into(),
                display_name: "X".into(),
                description: None,
                github_url: None,
                github_org: None,
                github_repo: None,
                source_kind: None,
                popularity_tier: "emerging".into(),
                popularity_score: 0,
                latest_scan_score: Some(90),
                latest_scan_tier: Some(crate::api::dto::Tier::Green),
                latest_scan_at: None,
                findings_count: 0,
                registries: vec![],
                agent_compatibility: vec![],
                updated_at: None,
            }],
            next_cursor: None,
            total_count: 1,
            page: 1,
            total_pages: 1,
            page_size: 50,
        }
    }

    #[test]
    fn typing_in_query_edits_and_debounces_list() {
        let mut st = state();
        let out = handle_key(&mut st, key(KeyCode::Char('r')));
        assert_eq!(st.query, "r");
        assert!(out.debounce_list);
        assert!(out.debounce_preview);
        assert!(!out.refetch_now);
    }

    #[test]
    fn ctrl_c_cancels_anywhere() {
        let mut st = state();
        handle_key(&mut st, ctrl(KeyCode::Char('c')));
        assert!(st.cancelled);
    }

    #[test]
    fn ctrl_f_toggles_filter_focus() {
        let mut st = state();
        handle_key(&mut st, ctrl(KeyCode::Char('f')));
        assert_eq!(st.focus, Focus::Filters);
        handle_key(&mut st, ctrl(KeyCode::Char('f')));
        assert_eq!(st.focus, Focus::Query);
    }

    #[test]
    fn enter_accepts_in_query_focus() {
        let mut st = state();
        handle_key(&mut st, key(KeyCode::Enter));
        assert!(st.accepted);
    }

    #[test]
    fn esc_in_filters_returns_to_query_not_cancel() {
        let mut st = state();
        st.set_focus(Focus::Filters);
        handle_key(&mut st, key(KeyCode::Esc));
        assert_eq!(st.focus, Focus::Query);
        assert!(!st.cancelled);
    }

    #[test]
    fn space_in_filters_toggles_facet_and_refetches() {
        let mut st = state();
        st.set_focus(Focus::Filters); // cursor at Kind(0) = skill
        let out = handle_key(&mut st, key(KeyCode::Char(' ')));
        assert!(out.refetch_now);
        assert_eq!(st.facets.kinds, vec!["skill".to_string()]);
    }

    #[test]
    fn arrows_adjust_score_only_on_score_facet() {
        let mut st = state();
        st.set_focus(Focus::Filters);
        // Move to the Score facet and bump it up.
        st.facet_cursor = state::FACET_COUNT - 2; // Score
        assert_eq!(st.current_facet(), FacetItem::Score);
        let out = handle_key(&mut st, key(KeyCode::Right));
        assert!(out.refetch_now);
        assert_eq!(st.facets.min_score, 5);
    }

    #[test]
    fn typing_letter_in_filters_jumps_to_query() {
        let mut st = state();
        st.set_focus(Focus::Filters);
        let out = handle_key(&mut st, key(KeyCode::Char('x')));
        assert_eq!(st.focus, Focus::Query);
        assert_eq!(st.query, "x");
        assert!(out.debounce_list);
    }

    #[test]
    fn tab_marks_in_query_focus() {
        let mut st = state();
        let seq = st.next_list_seq();
        st.apply_results(seq, one_item_env());
        handle_key(&mut st, key(KeyCode::Tab));
        assert!(st.is_marked("a--b--skill-x"));
    }

    #[test]
    fn apply_msg_handles_list_ok_and_err() {
        let mut st = state();
        let seq = st.next_list_seq();
        apply_msg(
            ApiMsg::List {
                seq,
                result: Box::new(Ok(one_item_env())),
            },
            &mut st,
        );
        assert_eq!(st.candidates.len(), 1);
        // An error on the latest seq surfaces a message.
        let seq2 = st.next_list_seq();
        apply_msg(
            ApiMsg::List {
                seq: seq2,
                result: Box::new(Err(SsError::new(ERR_BUG, "boom"))),
            },
            &mut st,
        );
        assert_eq!(st.error.as_deref(), Some("boom"));
    }

    #[test]
    fn apply_msg_handles_preview_ok_and_err() {
        let mut st = state();
        let seq = st.next_list_seq();
        st.apply_results(seq, one_item_env());
        let pseq = st.next_preview_seq();
        apply_msg(
            ApiMsg::Preview {
                seq: pseq,
                slug: "a--b--skill-x".into(),
                result: Box::new(Ok(ItemDetailResponse {
                    item: st.candidates[0].clone(),
                    latest_scan: None,
                })),
            },
            &mut st,
        );
        assert!(st.current_preview().is_some());
        // A preview error just clears the loading flag.
        let pseq2 = st.next_preview_seq();
        apply_msg(
            ApiMsg::Preview {
                seq: pseq2,
                slug: "a--b--skill-x".into(),
                result: Box::new(Err(SsError::new(ERR_BUG, "x"))),
            },
            &mut st,
        );
        assert!(!st.loading.preview);
    }

    #[test]
    fn schedule_preview_arms_only_when_target_exists() {
        let mut st = state();
        let mut pending: Option<Instant> = None;
        // No candidates → no target → no arm.
        schedule_preview(&st, &mut pending);
        assert!(pending.is_none());
        // With a highlighted uncached row → armed.
        let seq = st.next_list_seq();
        st.apply_results(seq, one_item_env());
        schedule_preview(&st, &mut pending);
        assert!(pending.is_some());
    }

    #[test]
    fn apply_outcome_debounces_list_without_dispatch() {
        let api = Api::new("http://127.0.0.1:1".into()).unwrap();
        let (tx, _rx) = mpsc::channel::<ApiMsg>(4);
        let mut st = state();
        let mut pl: Option<Instant> = None;
        let mut pp: Option<Instant> = None;
        let out = KeyOutcome {
            debounce_list: true,
            refetch_now: false,
            debounce_preview: false,
        };
        apply_outcome(&api, &mut st, &tx, out, &mut pl, &mut pp);
        assert!(pl.is_some());
    }

    #[tokio::test]
    async fn dispatch_round_trips_through_channel() {
        // Points at a closed port → the spawned fetch errors fast, exercising the
        // dispatch closures + the apply_msg error paths end to end.
        let api = Api::new("http://127.0.0.1:1".into()).unwrap();
        let (tx, mut rx) = mpsc::channel::<ApiMsg>(4);
        let mut st = state();
        let seq = st.next_list_seq();
        st.apply_results(seq, one_item_env());
        dispatch_list(&api, &mut st, &tx);
        dispatch_preview(&api, &mut st, &tx);
        for _ in 0..2 {
            if let Some(msg) = rx.recv().await {
                apply_msg(msg, &mut st);
            }
        }
    }
}
