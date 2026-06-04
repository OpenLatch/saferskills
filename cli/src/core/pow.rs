//! Proof-of-Work solver for the CLI scan-submit gate (I-05, D-05-30).
//!
//! The CLI can't solve a Cloudflare Turnstile CAPTCHA, so the API issues a
//! stateless HMAC-signed challenge that the CLI brute-forces and replays in the
//! `X-SaferSkills-CLI-PoW` header. This module is the solver half.
//!
//! ══ WIRE BYTE-LAYOUT (MUST match the backend `app/services/cli_pow.py`) ══
//!
//! The server hands us an opaque `challenge` string of the form
//! `"<payload_b64>.<mac>"`. We treat it as opaque bytes and find a `solution`
//! (an ASCII decimal string, NO '.') such that:
//!
//! ```text
//! sha256( (challenge + solution).as_bytes() )   // NO separator between them
//! ```
//!
//! has at least `difficulty` leading ZERO BITS (most-significant-bit-first). The
//! header we send back is `"<challenge>.<solution>"` — the ONLY '.' added here is
//! the one joining the challenge to the solution; the hashed bytes never contain
//! that joining dot.

/// Hard cap on the difficulty we will attempt — a hostile/buggy server cannot
/// make the CLI spin forever (the backend caps at 28 too).
pub const MAX_DIFFICULTY: u32 = 28;

/// Hard cap on solver iterations (a safety backstop well above the expected
/// `~2^difficulty` work at the 28-bit ceiling is impractical, so we bound it to
/// keep a pathological challenge from hanging — `obtain_pow` surfaces the miss).
const MAX_ITERATIONS: u64 = 1 << 30; // ~1.07e9

/// Count most-significant leading zero bits of a 32-byte SHA-256 digest.
pub fn leading_zero_bits(digest: &[u8; 32]) -> u32 {
    let mut bits = 0u32;
    for &byte in digest {
        if byte == 0 {
            bits += 8;
        } else {
            // u8::leading_zeros() already counts within 8 bits (0..=8).
            bits += byte.leading_zeros();
            break;
        }
    }
    bits
}

/// Brute-force a solution for `challenge` clearing `difficulty` leading zero
/// bits. Returns `None` if `difficulty` exceeds [`MAX_DIFFICULTY`] or the
/// iteration cap is hit (a hostile/impossible challenge).
pub fn solve(challenge: &str, difficulty: u32) -> Option<String> {
    use sha2::{Digest, Sha256};

    if difficulty > MAX_DIFFICULTY {
        return None;
    }
    let prefix = challenge.as_bytes();
    let mut n: u64 = 0;
    while n < MAX_ITERATIONS {
        let solution = n.to_string();
        let mut hasher = Sha256::new();
        hasher.update(prefix);
        hasher.update(solution.as_bytes());
        let digest: [u8; 32] = hasher.finalize().into();
        if leading_zero_bits(&digest) >= difficulty {
            return Some(solution);
        }
        n += 1;
    }
    None
}

/// Solve off the async reactor (`spawn_blocking`) — the CPU-bound loop must
/// never block other tasks. Returns `None` on the same conditions as [`solve`]
/// (or if the blocking task is cancelled).
pub async fn solve_async(challenge: String, difficulty: u32) -> Option<String> {
    tokio::task::spawn_blocking(move || solve(&challenge, difficulty))
        .await
        .ok()
        .flatten()
}

/// Build the `X-SaferSkills-CLI-PoW` header value: `"<challenge>.<solution>"`.
pub fn header_value(challenge: &str, solution: &str) -> String {
    format!("{challenge}.{solution}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};

    fn lzb_of(challenge: &str, solution: &str) -> u32 {
        let mut h = Sha256::new();
        h.update(challenge.as_bytes());
        h.update(solution.as_bytes());
        let d: [u8; 32] = h.finalize().into();
        leading_zero_bits(&d)
    }

    #[test]
    fn leading_zero_bits_counts_correctly() {
        let mut d = [0u8; 32];
        assert_eq!(leading_zero_bits(&d), 256);
        d[0] = 0x80; // 1000_0000 → 0 leading zero bits
        assert_eq!(leading_zero_bits(&d), 0);
        d[0] = 0x01; // 0000_0001 → 7 leading zero bits
        assert_eq!(leading_zero_bits(&d), 7);
        d[0] = 0x00;
        d[1] = 0x40; // 8 + 1 = 9
        assert_eq!(leading_zero_bits(&d), 9);
    }

    #[test]
    fn solve_meets_difficulty() {
        let challenge = "payload_b64.deadbeefmac";
        let difficulty = 12;
        let solution = solve(challenge, difficulty).expect("solvable at difficulty 12");
        // The returned solution genuinely clears the bar (matches the verify math).
        assert!(lzb_of(challenge, &solution) >= difficulty);
    }

    #[test]
    fn solve_rejects_excessive_difficulty() {
        assert!(solve("x.y", MAX_DIFFICULTY + 1).is_none());
    }

    #[test]
    fn header_value_joins_with_dot() {
        assert_eq!(header_value("a.b", "123"), "a.b.123");
    }
}
