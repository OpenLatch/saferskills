# Changelog

## Unreleased

### Changed

* **cli:** `install` is reshaped around the **aggregate score**. Every install now
  prints a **digest** (global score + tier + the 5-axis Security / Supply chain /
  Maintenance / Transparency / Community breakdown, mirroring `scan`), then
  **discloses which agents** it will write to (the default is every detected &
  compatible agent), then applies a **score gate**: an item scoring below
  `min_score` (default **90**) — or an unscored item — warns and requires a
  confirm, and a **red-tier (`< 40`)** item requires typing the item name. This
  **replaces** the previous finding-severity gate (the `gate_threshold` config key
  is removed). `--yes`/`--force` bypass the below-threshold confirm; only `--force`
  bypasses the red-tier type-name gate. New `min_score` config key +
  `SAFERSKILLS_MIN_SCORE` env override (precedence env > config > 90). `install
  --json` additionally emits `sub_scores`, `min_score`, the resolved target
  `agents`, and the `gate` decision (D-05-19).
* **cli:** `scan --local` now also audits **slash commands, subagents, and the
  full Claude plugin cache** — closing a major coverage gap (a real install jumps
  from ~12 audited capabilities to 100+). Claude `commands/*.md` + `agents/*.md`,
  Codex `prompts/*.md`, and Gemini `commands/*.toml` are scored as Skills (a
  namespaced command keeps its `lde:x` name); each installed plugin's
  active-version bundle is decomposed into its nested skills, MCP servers, hooks,
  commands, agents, and manifest as separate capabilities. The pre-flight shows a
  `· N from plugins` hint. CLI-only — no backend/schema change. (Bundle entry
  budget is pinned to the backend's per-upload entry cap so a deep plugin cache
  trims gracefully instead of being rejected.)
* **cli:** `scan --local` audits every capability **actually installed across
  your detected agents** (skills, MCP servers, hooks, rules) instead of the CLI's
  own install ledger — discovered from each agent's own config, bundled into one
  size-controlled `.zip`, scanned in a single run, and rendered as a rich
  per-capability audit report (verdict, category bars, an **Agents detected**
  section listing every detected agent + its config location and capability
  count — empty agents shown as `no capabilities found`, matching `doctor` —
  worst-first capabilities, most-problematic findings). `--private` keeps the run unlisted; `--detailed`
  expands per-capability axis bars + inline findings. The same rich report now
  renders for `scan <path>` and `scan <url>` too (D-05-27).

## [0.1.1](https://github.com/OpenLatch/saferskills/compare/v0.1.0...v0.1.1) (2026-06-08)


### Added

* CLI UX polish, catalog pagination & API reload-hang fix ([#74](https://github.com/OpenLatch/saferskills/issues/74)) ([9320d1b](https://github.com/OpenLatch/saferskills/commit/9320d1bff301eace3301bc312b7fa5ea85968eaa))
* **cli:** agent detection, config writers & install lifecycle (I-05 Phase B) ([#66](https://github.com/OpenLatch/saferskills/issues/66)) ([7d26b6b](https://github.com/OpenLatch/saferskills/commit/7d26b6b5906ecc404453046edf811ee01a41da25))
* **cli:** install every capability kind across all agents (+install_spec) ([#82](https://github.com/OpenLatch/saferskills/issues/82)) ([de84569](https://github.com/OpenLatch/saferskills/commit/de8456974609f268fe353a132945363bf92a74b4))
* **cli:** interactive `search` TUI finder + installer ([#78](https://github.com/OpenLatch/saferskills/issues/78)) ([b24297a](https://github.com/OpenLatch/saferskills/commit/b24297a00443aba9fe6ad442b878ca83841ea8df))
* **cli:** scan matrix, SEO surfaces & ingestion concurrency hardening (I-05 Phase C) ([#71](https://github.com/OpenLatch/saferskills/issues/71)) ([381b927](https://github.com/OpenLatch/saferskills/commit/381b9272eb1283fc1f10dbcdcf5e339e40bff711))
* observability stack (Sentry/PostHog/OTel) + severity ceiling & catalog activity ([#75](https://github.com/OpenLatch/saferskills/issues/75)) ([2ce7d3c](https://github.com/OpenLatch/saferskills/commit/2ce7d3c26449b06ed46ece2b4a3dd401cf1d555f))
* **scan:** hybrid repo fetch — Git Trees + raw for large repos ([#73](https://github.com/OpenLatch/saferskills/issues/73)) ([1f382ab](https://github.com/OpenLatch/saferskills/commit/1f382abb4706ce9c871eeb7fb5be7071bfc47d86))

## [0.1.0](https://github.com/OpenLatch/saferskills/compare/v0.0.2-placeholder...v0.1.0) (2026-06-04)


### Added

* **cli:** rust core, distribution rails & read commands (I-05 Phase A) ([#59](https://github.com/OpenLatch/saferskills/issues/59)) ([59d2994](https://github.com/OpenLatch/saferskills/commit/59d29943719c777e924683729a78963d0a5cd68d))
* **frontend:** visual-fidelity pass + dual-mode scan telemetry (I-3.5) ([#39](https://github.com/OpenLatch/saferskills/issues/39)) ([167dd37](https://github.com/OpenLatch/saferskills/commit/167dd37e5a8119d058a4ca9e84314a621ab06ed4))
* **scan:** phase A — data + rubric + seed rules + FP harness ([#16](https://github.com/OpenLatch/saferskills/issues/16)) ([fdd2b1f](https://github.com/OpenLatch/saferskills/commit/fdd2b1ffda217cc2a8b62d9352f67c490f1e8b23))


### Documentation

* **cli:** note source builds send no telemetry ([#63](https://github.com/OpenLatch/saferskills/issues/63)) ([3474d66](https://github.com/OpenLatch/saferskills/commit/3474d664eea7639db229e285ba00612aed47db4f))

## [0.0.2-placeholder](https://github.com/OpenLatch/saferskills/compare/v0.0.1-placeholder...v0.0.2-placeholder) (2026-05-26)


### Documentation

* adopt "every AI capability, independently scanned" headline ([#9](https://github.com/OpenLatch/saferskills/issues/9)) ([91fdd0b](https://github.com/OpenLatch/saferskills/commit/91fdd0bd3e47d88b5bf02f9d4a8128116c84b3a0))

## [0.0.1-placeholder](https://github.com/OpenLatch/saferskills/compare/v0.0.0-placeholder...v0.0.1-placeholder) (2026-05-26)


### Added

* build surface (I-01 Phase B) ([87fda2b](https://github.com/OpenLatch/saferskills/commit/87fda2b65fbd44133a3a64b5df77936f9c9f48d7))
* **ci:** npm Trusted Publisher + release-please pipeline ([#4](https://github.com/OpenLatch/saferskills/issues/4)) ([bbdd6b0](https://github.com/OpenLatch/saferskills/commit/bbdd6b0ad40cddc0b72b8b80fc7d79e4126b2a0c))
