# Operator deletion runbook — abusive PUBLIC upload

> This is the
> **only** removal path for an abusive **public** upload. Uploads have **no
> vendor right-of-reply** (see `.claude/rules/vendor-appeals.md`); unlisted runs
> self-serve deletion via `DELETE /api/v1/scans/r/{token}`. There is **no**
> takedown endpoint, automated path, or Slack alert (deferred — founder).

A maintainer runs this manual SQL against the **production** DB to remove a
public upload that violates policy. It invokes the same ordered logic as
`app/scan/persistence.py::delete_run_cascade(..., allow_public=True)` and
additionally deletes the canonical `catalog_item` the upload created (which the
routine intentionally leaves, since `owner_run_id IS NULL` on a canonical row).

## Why manual SQL (not an endpoint)

The repo has no executable vendor-appeals deletion path — only policy docs. The
founder accepts manual DB deletion for the rare abusive public upload. Building a
moderation UI / automated takedown is out of scope.

## Procedure

1. **Identify the run.** From the public report URL `/scans/<run_id>` take the
   `<run_id>`. Confirm it is a public upload:

   ```sql
   SELECT id, source_kind, visibility, original_filename, content_hash_sha256
   FROM scan_runs WHERE id = '<run_id>';
   -- expect: source_kind='upload', visibility='public'
   ```

2. **Capture the canonical catalog_item id(s)** the upload created (one per
   capability — a `.zip` can have several):

   ```sql
   SELECT DISTINCT ci.id, ci.slug
   FROM catalog_items ci
   JOIN scans s ON s.catalog_item_id = ci.id
   WHERE s.scan_run_id = '<run_id>' AND ci.owner_run_id IS NULL;
   ```

3. **Delete in order** (the `scans -> scan_runs` FK is `ON DELETE SET NULL`, so
   scans MUST go before the run — never rely on the FK). Run as ONE transaction:

   ```sql
   BEGIN;

   -- findings of the run's scans
   DELETE FROM findings
   WHERE scan_id IN (SELECT id FROM scans WHERE scan_run_id = '<run_id>');

   -- progress events
   DELETE FROM scan_events WHERE scan_run_id = '<run_id>';

   -- the per-capability scans
   DELETE FROM scans WHERE scan_run_id = '<run_id>';

   -- shadow rows (none for a public run, but harmless + matches the routine)
   DELETE FROM catalog_items WHERE owner_run_id = '<run_id>';

   -- per-run upload bytes (public uploads store in artifact_blobs, but a
   -- defensively-present row would be cleared here)
   DELETE FROM upload_files WHERE scan_run_id = '<run_id>';

   -- the canonical catalog item(s) this public upload created (step 2 ids)
   DELETE FROM catalog_items WHERE id IN ('<canonical_item_id>' /*, ... */);

   -- the run itself
   DELETE FROM scan_runs WHERE id = '<run_id>';

   COMMIT;
   ```

4. **Blobs are reclaimed later.** `artifact_blobs` is content-addressed + deduped
   — never hard-deleted inline (another scan/item may share a blob). The
   unreferenced-`artifact_blobs` background sweep reclaims any now-orphaned blob.

## Safety notes

- **Public runs only.** The token-delete route + the expiry sweep call
  `delete_run_cascade(allow_public=False)` and refuse a public run; this runbook
  is the sole caller that targets a public upload.
- **Irreversible.** There is no undo — confirm the `run_id` before `COMMIT`.
- **Audit.** Record the action (run_id, reason, operator, date) per
  `.claude/rules/security.md` § Audit Trail.
