"""Agent Scan subsystem (I-5.5).

The lean crypto + pack-assembly core for the behavioral agent scan: per-run
canary derivation (`canary`), sign-the-served-bytes pack signing (`signing`),
the one-time submit/run token (`run_token`), per-run pack assembly (`pack`), and
run-create persistence (`persistence`). Grading + scoring land in Phase 2.

Prime invariants (see `2026-06-09-design.md` §3): the agent never self-grades,
no LLM in the verdict path, no raw artifact payload in any trace / on
`agent_findings`, lean crypto (one key, sign-served-bytes, stdlib canary).
"""
