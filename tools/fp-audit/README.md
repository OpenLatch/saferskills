<div align="center">

<a href="../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>False-positive audit harness</h3>
<p>Per-rule FP-rate measurement that gates shadow→active rule promotion.</p>

</div>

## What it is

The false-positive audit harness implements the FP-audit spec: per-rule FP-rate measurement against a 100-item hand-labelled [fixture suite](./fixtures/README.md). Promotion gate — a `status: shadow` rule with an FP rate <10% on the fixture suite advances to `status: active`.

## Commands

```bash
cd tools/fp-audit && uv sync

# Dry-run against the fixture suite (stubs the engine call — returns
# "engine not yet wired" until the detector is wired in).
uv run fp-audit run --dry-run

# Real run against all rules (once the engine is wired in).
uv run fp-audit run --all

# Or against a single rule.
uv run fp-audit run --rule SS-SKILL-INJECT-IGNORE-01

# Add a new fixture.
uv run fp-audit add-fixture https://github.com/example/repo --label good

# Generate the rendered FP-audit report.
uv run fp-audit report --output fp_audit_report.json
```

## Fixture format

Each fixture is a directory under `fixtures/known-good/` or `fixtures/known-bad/` plus an entry in the directory's `manifest.yaml`:

```yaml
- path: example-org--clean-skill
  source_url: https://github.com/example-org/clean-skill
  expected_score_range: [80, 100]     # for known-good only
  hash_at_capture: <sha256 of fixture tarball when captured>
  notes: "Anthropics skill, clean text-only SKILL.md, passive prompts."
```

Add a new known-good fixture by:

1. Cloning the upstream repo at the chosen ref.
2. Anonymising any PII (replace real maintainer emails, etc.).
3. Removing files non-essential to the scan (`.git/`, large binary blobs, vendored deps).
4. Placing the resulting directory under `fixtures/known-good/<slug>/`.
5. Adding an entry to `fixtures/known-good/manifest.yaml`.
6. Citing the source clearly in the entry's `notes`.

## Promotion gate

The runner compares each rule's FP rate (over the 50-good fixture set) against `thresholds.yaml` (default 10%, per-rule overrides supported). The decision appears in the report's `per_rule[*].decision` field — `promote_to_active`, `active_confirmed`, `shadow_extended`, `demote_to_shadow`, or `deferred_engine_unavailable`. The report shape is locked in [`../../schemas/fp-audit-report.schema.json`](../../schemas/fp-audit-report.schema.json).

## Current scope

The initial release lands the CLI surface + 100 stub fixture entries (manifests only; fixture content is added as the engine matures in a later release). The runner detects the absent engine module and emits a `deferred_engine_unavailable` decision for every rule; the CLI exit code is 0 in this state so the CI lane stays green.

## See also

- [`fixtures/README.md`](./fixtures/README.md) — the 100-item hand-labelled regression suite
- [`rubric/README.md`](../../rubric/README.md) — the rules this harness gates
- [`.claude/rules/methodology.md`](../../.claude/rules/methodology.md) — the shadow→active lifecycle

---

<sub>Part of **[SaferSkills](../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
