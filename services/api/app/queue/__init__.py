"""In-process scan queue.

No Procrastinate, no Celery, no Redis — per `.claude/rules/tech-stack.md`. Each
scan is driven by an `asyncio.create_task` spawned from the POST /scans
endpoint. The worker emits per-stage progress events on the `scan_events`
table + a PostgreSQL `NOTIFY scan_progress_<id>` so SSE consumers can stream
live deltas.

For production resilience: `recover_stale_scans` runs at app startup to
re-enqueue any scan whose status has been `running` for >5 minutes (a Fly
machine restart mid-scan would otherwise orphan it).
"""

from app.queue.scan_runner import scan_run, scan_run_repo

__all__ = ["scan_run", "scan_run_repo"]
