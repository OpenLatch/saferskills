//! Memorable agent-scan codenames (`swift-otter`) — replaces the old `my-agent`
//! placeholder so every scanned agent gets a distinct, human-rememberable card.
//!
//! The name is **stable per machine + platform**: the first scan of a platform
//! rolls an `adjective-noun` codename and persists it in
//! `~/.saferskills/agent-names.json` (`{platform → name}`); later scans of that
//! platform reuse it. A user-supplied `--name` overrides the codename; on a
//! multi-platform run an explicit name gets the platform appended so the cards
//! stay distinct (`prod-bot-cursor`).
//!
//! Randomness is std-only (no `rand` crate — keeps the binary lean + the
//! `cli-rustls` lane untouched): a `DefaultHasher` seeded over the wall-clock
//! nanos, the pid, the platform, and a re-roll salt. Because the roll is
//! persisted on first use, weak seeding is harmless — variety on the first roll
//! is all that's needed.

use std::collections::hash_map::DefaultHasher;
use std::collections::{BTreeMap, HashSet};
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::core::config::{atomic_write, saferskills_dir};

/// Max display-name length (mirrors the backend `agent_name` `max_length=200`).
const MAX_NAME_LEN: usize = 200;

const ADJECTIVES: &[&str] = &[
    "swift", "lucid", "amber", "quiet", "brave", "clever", "cosmic", "golden", "hidden", "jolly",
    "keen", "lively", "mellow", "nimble", "polar", "rapid", "royal", "sage", "silent", "solar",
    "stellar", "sturdy", "sunny", "vivid", "witty", "zesty", "bold", "bright", "crisp", "daring",
    "eager", "fancy", "gentle", "humble", "ivory", "lunar", "merry", "noble", "plucky", "proud",
    "rustic", "shiny", "spry", "tidy", "urban", "valiant", "wily", "zen",
];

const NOUNS: &[&str] = &[
    "otter", "falcon", "heron", "badger", "lynx", "marten", "gecko", "ibis", "koala", "lemur",
    "manta", "narwhal", "ocelot", "panther", "quokka", "raven", "salmon", "tapir", "urchin",
    "vulture", "walrus", "yak", "zebra", "beaver", "cobra", "dingo", "egret", "ferret", "gibbon",
    "hawk", "jackal", "kestrel", "llama", "magpie", "newt", "osprey", "puffin", "quail", "rabbit",
    "seal", "toucan", "urial", "viper", "weasel", "wombat", "fox", "mole", "owl",
];

/// `~/.saferskills/agent-names.json` — the per-platform codename store.
fn names_path() -> PathBuf {
    saferskills_dir().join("agent-names.json")
}

/// Load the `{platform → name}` map; a missing / corrupt file is an empty map
/// (the name just gets re-rolled — never an error that breaks a scan).
fn load_from(path: &Path) -> BTreeMap<String, String> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

/// Best-effort persist — a write failure must not break the scan (the name is
/// still used for this run; it just won't be remembered next time).
fn persist_to(path: &Path, map: &BTreeMap<String, String>) {
    if let Ok(body) = serde_json::to_vec_pretty(map) {
        let _ = atomic_write(path, body.as_slice());
    }
}

fn truncate(s: &str) -> String {
    s.chars().take(MAX_NAME_LEN).collect()
}

/// A `u64` seed from the wall clock, the pid, the platform, and a re-roll salt.
fn seed(platform: &str, salt: u64) -> u64 {
    let mut h = DefaultHasher::new();
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0)
        .hash(&mut h);
    std::process::id().hash(&mut h);
    platform.hash(&mut h);
    salt.hash(&mut h);
    h.finish()
}

/// One `adjective-noun` roll for `platform` at `salt`.
fn roll(platform: &str, salt: u64) -> String {
    let s = seed(platform, salt);
    let adj = ADJECTIVES[(s as usize) % ADJECTIVES.len()];
    let noun = NOUNS[((s >> 32) as usize) % NOUNS.len()];
    format!("{adj}-{noun}")
}

/// Roll a codename for `platform` that isn't already taken by `existing` (so two
/// platforms rolled microseconds apart in one invocation don't collide).
fn generate(platform: &str, existing: &BTreeMap<String, String>) -> String {
    let taken: HashSet<&str> = existing.values().map(String::as_str).collect();
    for salt in 0..64u64 {
        let candidate = roll(platform, salt);
        if !taken.contains(candidate.as_str()) {
            return candidate;
        }
    }
    // Pathologically saturated — disambiguate with a short hex suffix.
    format!("{}-{:x}", roll(platform, 0), seed(platform, 999) & 0xfff)
}

/// Pure resolution given the already-loaded `existing` map. Returns the resolved
/// name and whether it is a freshly-rolled codename that should be persisted.
fn pick(
    platform: &str,
    override_name: Option<&str>,
    multi: bool,
    existing: &BTreeMap<String, String>,
) -> (String, bool) {
    if let Some(name) = override_name {
        let name = name.trim();
        if !name.is_empty() {
            let full = if multi {
                format!("{name}-{platform}")
            } else {
                name.to_string()
            };
            return (truncate(&full), false);
        }
    }
    if let Some(existing_name) = existing.get(platform) {
        return (existing_name.clone(), false);
    }
    (generate(platform, existing), true)
}

/// Resolve the display name for a scanned `platform`:
/// - `override_name` (the `--name` flag) wins — verbatim for a single target, or
///   `<name>-<platform>` on a multi-platform run so the cards stay distinct;
/// - otherwise reuse the persisted per-platform codename, or roll + persist a new
///   one (stable per machine + platform thereafter).
pub fn resolve_agent_name(platform: &str, override_name: Option<&str>, multi: bool) -> String {
    let path = names_path();
    let mut map = load_from(&path);
    let (name, is_new) = pick(platform, override_name, multi, &map);
    if is_new {
        map.insert(platform.to_string(), name.clone());
        persist_to(&path, &map);
    }
    name
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn override_single_is_verbatim() {
        let (name, is_new) = pick("claude-code", Some("prod-bot"), false, &BTreeMap::new());
        assert_eq!(name, "prod-bot");
        assert!(!is_new);
    }

    #[test]
    fn override_multi_appends_platform() {
        let (name, is_new) = pick("cursor", Some("prod-bot"), true, &BTreeMap::new());
        assert_eq!(name, "prod-bot-cursor");
        assert!(!is_new);
    }

    #[test]
    fn override_trims_and_blank_falls_through() {
        let (name, _) = pick("claude-code", Some("  spaced  "), false, &BTreeMap::new());
        assert_eq!(name, "spaced");
        // Whitespace-only override is ignored → a generated codename.
        let (gen, is_new) = pick("claude-code", Some("   "), false, &BTreeMap::new());
        assert!(is_new);
        assert!(gen.contains('-'));
    }

    #[test]
    fn existing_codename_is_reused() {
        let mut map = BTreeMap::new();
        map.insert("claude-code".to_string(), "swift-otter".to_string());
        let (name, is_new) = pick("claude-code", None, false, &map);
        assert_eq!(name, "swift-otter");
        assert!(!is_new);
    }

    #[test]
    fn generated_codename_has_adjective_noun_shape() {
        let (name, is_new) = pick("claude-code", None, false, &BTreeMap::new());
        assert!(is_new);
        let (adj, noun) = name.split_once('-').expect("adjective-noun");
        assert!(ADJECTIVES.contains(&adj), "{adj} not an adjective");
        assert!(NOUNS.contains(&noun), "{noun} not a noun");
    }

    #[test]
    fn generate_avoids_collision_with_existing() {
        // Saturate `existing` with one platform's roll; a second roll must differ.
        let first = generate("claude-code", &BTreeMap::new());
        let mut existing = BTreeMap::new();
        existing.insert("other".to_string(), first.clone());
        let second = generate("claude-code", &existing);
        assert_ne!(first, second);
    }

    #[test]
    fn override_is_truncated_to_max_len() {
        let long = "x".repeat(300);
        let (name, _) = pick("claude-code", Some(&long), false, &BTreeMap::new());
        assert_eq!(name.chars().count(), MAX_NAME_LEN);
    }

    #[test]
    fn persist_round_trips() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("agent-names.json");
        assert!(load_from(&path).is_empty());
        let mut map = BTreeMap::new();
        map.insert("claude-code".to_string(), "swift-otter".to_string());
        persist_to(&path, &map);
        let loaded = load_from(&path);
        assert_eq!(
            loaded.get("claude-code").map(String::as_str),
            Some("swift-otter")
        );
    }
}
