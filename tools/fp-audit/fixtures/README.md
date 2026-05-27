# `fixtures/` — FP-audit fixture suite

Per locked decision **D-21**: 100 hand-labelled fixtures (50 known-good + 50
known-bad) form the regression bed for the FP-audit harness.

## Layout

```
fixtures/
├── known-good/
│   ├── manifest.yaml                # 50 entries (source URL, expected
│   │                                # score band, capture hash, notes)
│   └── <slug>/                      # per-fixture directory (Phase B onward)
└── known-bad/
    ├── manifest.yaml                # 50 entries — synthetic seeds + ClawHavoc
    │                                # PoC samples (research-fair-use)
    └── <slug>/                      # per-fixture directory (Phase B onward)
```

Phase A ships **manifest entries only** (D-21 + clarification). The actual
fixture content lands as Phase B onboards each fixture (clone, anonymise,
content-hash, commit). The runner detects unpopulated fixtures and reports
`deferred_engine_unavailable` for every rule until the engine ships.

## Adding a fixture

```bash
uv run fp-audit add-fixture https://github.com/example/repo --label good --notes "Clean Anthropics-skill sample"
```

This appends an entry to the right manifest; the maintainer then clones the
fixture content into the directory referenced by `path`, computes the
`hash_at_capture` SHA-256, and updates the manifest.

## Sourcing posture

- **Known-good (50)**: drawn from `anthropics/skills` (Apache-2.0), curated
  MCP registry entries, hand-picked clean rules/hooks/plugins from public
  registries. All sources cited per-fixture in `notes`.
- **Known-bad (50)**: synthetic adversarial samples authored by SaferSkills
  for this audit (Unicode-tag injection, BiDi smuggling, base64-shell, etc.)
  plus a curated subset of ClawHavoc PoC corpus entries (research-fair-use,
  cited).

No fixture should contain functional credentials, real PII, or a live
exploit harness. Synthetic samples are documented in-line.

## Promotion gate

See [`../thresholds.yaml`](../thresholds.yaml) and
[`../README.md`](../README.md) § Promotion gate.
