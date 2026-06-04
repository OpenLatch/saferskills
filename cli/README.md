# saferskills

**Every AI capability, independently scanned.** Install Skills and MCP servers to any AI agent with a verified SaferSkills trust score checked at install time.

```bash
npx saferskills info github-mcp        # see an item's score + findings
npx saferskills install github-mcp     # install to your detected agents (Phase B)
npx saferskills scan ./my-skill        # scan a local capability (Phase C)
```

No install required — `npx saferskills <command>` runs the prebuilt native binary. Or install it permanently:

```bash
npm install -g saferskills      # npm
cargo install saferskills       # crates.io
```

## What it does

SaferSkills scans Skills, MCP servers, hooks, and plugins for security, supply-chain, maintenance, transparency, and community signals — producing a public, methodology-backed trust score with a full rule trace. The CLI is a thin, fail-open client of the public API: reads are unauthenticated and uncapped, and the *safe path is the easy path*.

## Commands

| Command | Status | What it does |
|---|---|---|
| `info <name>` (alias `check`) | ✅ | Resolve a name → catalog item; print score, tier, findings, and the report URL. |
| `install <name>` | Phase B | Install a Skill / MCP server to your detected agents, gated by finding severity. |
| `uninstall <name>` | Phase B | Reverse exactly what an install wrote. |
| `update [--all]` | Phase B | Refresh installed capabilities; re-verify scores. |
| `list` | Phase B | Show installed capabilities with current scores. |
| `doctor` | Phase B | Diagnose registry-vs-filesystem drift. |
| `scan <path\|url>` | Phase C | Scan a local path or GitHub URL; print the report URL. |
| `completion <shell>` | ✅ | Print a shell completion script. |

## Global flags

`--json` (machine-readable output on stdout), `--no-color` / `--color <auto\|always\|never>`, `-v/--verbose`, `-q/--quiet`, `--yes`, `--force`, `--non-interactive` (alias `--no-input`).

Output discipline: **stdout is machine data** (JSON), **stderr is everything human** (steps, warnings, errors, the banner). Honors `NO_COLOR`, `CLICOLOR_FORCE`, and `TERM=dumb`.

## Configuration

State lives under `~/.saferskills/` (override with `SAFERSKILLS_DIR`):

- `config.toml` — `api_url`, `gate_threshold`, `telemetry`, `install_telemetry`.
- `installs.json` — the install registry.

The API origin resolves as `SAFERSKILLS_API_URL` env → `config.toml` `api_url` → `https://saferskills.ai`.

## Telemetry

Anonymous, opt-out usage analytics (which command ran, its exit code, a coarse duration — never arguments, names, paths, or any personal data). Disable with `SAFERSKILLS_NO_TELEMETRY=1`; `DO_NOT_TRACK` and `CI` are also honored. See <https://saferskills.ai/privacy>.

## Building from source

```bash
cd cli
cargo build --release          # → target/release/saferskills
cargo test
cargo clippy --all-targets -- -D warnings
```

TLS is rustls-only (no OpenSSL). The binary is a single ~5 MB executable with sub-second start.

## Publishing

Published via [npm Trusted Publishers (OIDC)](https://docs.npmjs.com/trusted-publishers) and [crates.io Trusted Publishing](https://crates.io) — no long-lived registry tokens in CI. The release path is `.github/workflows/publish-npm.yml`: it builds 5 platform binaries, signs them (cosign keyless) with SBOMs, publishes the scoped `@openlatch/saferskills-<platform>` packages + the unscoped `saferskills` main package, and the `saferskills` crate.

---

An OpenLatch project · <https://saferskills.ai>
