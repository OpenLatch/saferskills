//! Local fuzzy ranking of the loaded candidate pool (pure + tested).
//!
//! nucleo's synchronous matcher re-orders the already-loaded pool on every
//! keystroke at 0 ms latency (the pool is ≤ `limit` items, so a synchronous
//! score-and-sort is instant — no worker thread / `tick()` poll needed). The
//! debounced server refetch broadens the pool; this just orders what is loaded.
//!
//! An empty query preserves the server's sort order (the trending list), so the
//! default view is exactly what the API returned.

use nucleo::pattern::{CaseMatching, Normalization, Pattern};
use nucleo::{Config, Matcher, Utf32Str};

/// Rank `haystacks` against `query`, returning their indices best-match-first.
/// An empty/whitespace query returns every index in original order (preserving
/// the server sort). Non-matching haystacks are dropped from the result.
pub fn rank(query: &str, haystacks: &[String]) -> Vec<usize> {
    let q = query.trim();
    if q.is_empty() {
        return (0..haystacks.len()).collect();
    }
    let mut matcher = Matcher::new(Config::DEFAULT);
    let pattern = Pattern::parse(q, CaseMatching::Smart, Normalization::Smart);
    let mut buf: Vec<char> = Vec::new();
    let mut scored: Vec<(usize, u32)> = Vec::new();
    for (i, h) in haystacks.iter().enumerate() {
        let hs = Utf32Str::new(h, &mut buf);
        if let Some(score) = pattern.score(hs, &mut matcher) {
            scored.push((i, score));
        }
    }
    // Highest score first; ties keep the original (server-sorted) order.
    scored.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    scored.into_iter().map(|(i, _)| i).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_query_preserves_order() {
        let h = vec!["b".to_string(), "a".to_string(), "c".to_string()];
        assert_eq!(rank("", &h), vec![0, 1, 2]);
        assert_eq!(rank("   ", &h), vec![0, 1, 2]);
    }

    #[test]
    fn matches_are_ordered_and_non_matches_dropped() {
        let h = vec![
            "redis mcp server".to_string(),
            "postgres skill".to_string(),
            "redis cache helper".to_string(),
        ];
        let r = rank("redis", &h);
        // Both redis haystacks rank; the postgres one is dropped.
        assert!(r.contains(&0));
        assert!(r.contains(&2));
        assert!(!r.contains(&1));
    }

    #[test]
    fn closer_match_ranks_first() {
        let h = vec![
            "a-redis-thing-with-extra-words".to_string(),
            "redis".to_string(),
        ];
        let r = rank("redis", &h);
        // The exact short match should outrank the padded one.
        assert_eq!(r.first().copied(), Some(1));
    }

    #[test]
    fn no_match_returns_empty() {
        let h = vec!["alpha".to_string(), "beta".to_string()];
        assert!(rank("zzzzz", &h).is_empty());
    }
}
