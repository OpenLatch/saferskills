"""Scan engine — deterministic, methodology-driven detector runtime.

Public entry points:

- `rubric.RULES` — loaded at startup; mapping ruleId → RubricRule.
- `engine.run_scan(catalog_item_id, github_url, ref_sha, rubric_version)` — runs
  the full pipeline (fetch → walk → detect → score), returns ScanResult.
- `persistence.commit_scan(...)` — writes Scan + Findings to DB.

The runtime is in-process and synchronous within one stage (regex eval is CPU);
the queue worker drives stages with `asyncio.TaskGroup` per the no-Redis mandate
in `.claude/rules/tech-stack.md`.
"""
