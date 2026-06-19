"""Agent Scan subsystem.

The lean crypto + pack-assembly core for the behavioral agent scan: per-run
canary derivation (`canary`), sign-the-served-bytes pack signing (`signing`),
the one-time submit/run token (`run_token`), per-run pack assembly (`pack`), and
run-create persistence (`persistence`). Grading + scoring land separately.

Prime invariants: the agent never self-grades, no LLM in the verdict path,
no raw artifact payload in any trace / on `agent_findings`, lean crypto
(one key, sign-served-bytes, stdlib canary).
"""
