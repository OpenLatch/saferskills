---
paths:
  - 'ui/**'
  - 'webapp/src/components/**'
  - 'webapp/src/styles/**'
---

# Design System

## Purpose

The SaferSkills brand sits on the OpenLatch-shared teal palette (kinship-by-color) with a **distinct shape language** (chamfered hex caps + page-head + ridge dividers) and **distinct type stack** (DM Sans / Space Mono / Anybody / Nanum Pen Script + Onest 600 monochrome wordmark). The visual identity is locked per the Wordmark Spec lock 2026-05-27, which **supersedes** the original cobalt-primary direction.

Components live under `ui/` as framework-agnostic React 19 + Tailwind primitives + thin Astro shells; Astro routes mount them as islands.

## Tokens are the single source of truth

All visual tokens live in `ui/styles/tokens.css` — colors, radii, spacing, typography, motion, layout, signature background textures, hex-mask SVGs, score band colors. **Components never hardcode values; they reference tokens via CSS variables or Tailwind v4 utility classes mapped through the `@theme` block.** Tailwind v4 reads them via `@theme` directly from this file — there is no `tailwind.config.js`.

| Token | Value | Why |
|---|---|---|
| `--ol-brand-primary` | `#0D9488` (emerald teal) | SaferSkills brand color; kinship-by-color with OpenLatch master palette per Wordmark Spec lock 2026-05-27 |
| `--ol-brand-primary-dark` | `#0F766E` | Hover / active state |
| `--ol-brand-accent` | `#F97316` (warm orange) | Script-pen accents, ridge-pixel tick markers, hand-written decorations |
| `--score-green` / `--score-yellow` / `--score-orange` / `--score-red` | OpenSSF-style 4-band semantic colors | Tier color language: ≥80 / 60-79 / 40-59 / 0-39 |
| `--radius-0` | `0` | Squared corners across the entire system — never round a button |
| `--radius-xs` | `2px` | Form fields + chips (lone exception) |
| `--radius-pill` | `999px` | Badges only (used sparingly) |
| `--shadow-hairline` | `0 0 0 1px var(--color-ink)` | Single hairline borders, never thicker on UI chrome |
| `--focus-ring` | `0 0 0 2px var(--brand-primary)` | Keyboard `:focus-visible` ring on interactive DS atoms (SegmentedTabs / Toggle / DropZone) |
| `--shadow-stamp` | `4px 4px 0 0 var(--color-ink)` | Press-block emphasis on **non-interactive** cards + featured items, used sparingly. **Never on buttons or overlays/modals** — see § Brutalist offset shadows |
| `--shadow-overlay` | `0 18px 40px -24px` slate-900 (deeper in dark) | Soft ambient lift for **floating overlays/modals** (`.turnstile-gate`, `.confirm-dialog`) over a dimmed/blurred backdrop — the sanctioned modal-elevation exception to "no drop shadows". Subtle, never the brutalist offset. |
| `--ease-emphasized` | `cubic-bezier(0.23, 1, 0.32, 1)` | Emphasized decelerate for overlay/modal enter sequences — more "punch" than `--ease-out` |
| `--font-display` / `--font-sans` | `DM Sans` (400-800) | Body + display |
| `--font-mono` | `Space Mono` (400, 700) | Code + rule_ids + monospace meta |
| `--font-loud` | `Anybody` (variable, wdth=125, weight=800) | Score numbers + loud stat displays |
| `--font-script` | `Nanum Pen Script` | Hand-written orange accents (e.g. `~30s`, `live`) |
| `--font-wordmark` | `Onest` (SemiBold 600) | Wordmark only (single use, monochrome) |

Fonts ship via `@fontsource/*` packages (DM Sans, Space Mono, Onest, Nanum Pen Script) or `@fontsource-variable/anybody` for the variable-width display weight. **CDN-hosted fonts are forbidden** — the `validate` CI lane greps for `fonts.googleapis.com` and fails on any hit in `ui/styles/`, `webapp/src/styles/`, or `webapp/src/layouts/`.

## Component layout

```
ui/
├── components/
│   ├── atoms/        # Wordmark, Logo, Footer, Button, ButtonPair, GhStar, Chip, Badge, BandPill,
│   │                 # ScoreNumber, DotStrip, Sparkline (inline trend line — catalog Activity column),
│   │                 # Eyebrow, Breadcrumb, BracketLabel, Input, PageHead, RidgeStars,
│   │                 # RidgeFlow, RidgePixel, ThemeToggle, RotatingHeadline, Toast, CopyButton,
│   │                 # CopyIconButton (discreet icon-only copy — sha/scan-id, self-contained check flash),
│   │                 # EmailCaptureForm (retained — reused by I-06 magic-link surface),
│   │                 # SegmentedTabs, Toggle (I-3.5), Select (DS listbox — replaces native <select>),
│   │                 # Checkbox (DS checkbox/radio — token-driven, dark-correct),
│   │                 # Dialog (native <dialog> modal — was webapp ConfirmDialog),
│   │                 # RangeSlider (dual-thumb — was catalog ScoreRangeSlider),
│   │                 # SeverityPill (the 5-tier `.sev`/`.sw` severity chip — shared by
│   │                 #   FindingDetail + the /methodology RuleCard; defines its own Severity union),
│   │                 # FrameworkBadges (the OWASP/MITRE/CWE `.fw-badge` reference row — shared by
│   │                 #   FindingDetail + RuleCard; owns the family-label maps + FrameworkRef shape),
│   │                 # AgentVerb, TrustTierPill, CapCallout, EvidenceWithheldNote,
│   │                 #   StalePackBanner (I-5.6 Agent Report score-hero + lifecycle atoms),
│   │                 # RefChip, ProvenanceChips (I-5.6 Phase B — deep-linked ref chips + badge provenance)
│   ├── molecules/    # NavBar, CtaBand, AgentMarquee, WhyRow, InstallTabs, ActionCard,
│   │                 # RecentScanCard, TrendScanCard (Phase A1)
│   │                 # CatalogToolbar, CatalogFilterSide, CatalogResultsRow, ScanSplit,
│   │                 # ScanInput, ScanProgressBar, ScanStepper, ScanTerminal, ScanReportHero,
│   │                 # InstallCommandBox (Phase B)
│   │                 # ScoreHistoryChart, InstallActivity, RelatedItems, EmbedBadgeBox,
│   │                 # VendorResponseCard (Phase C)
│   │                 # DropZone (I-3.5 — animated upload state machine, D-UP-ANIM)
│   │                 # FindingDetail (the v3 `.find-card` — explainable finding, shared
│   │                 #   by repo scan + upload/item checklist; supersedes FindingRow + SubScoreAccordion)
│   │                 # ScoreBreakdownTable, MarkdownSourceViewer, CheckGroupList
│   │                 # (audit extraction — shared by ItemTabs + CapabilityReportTabs)
│   │                 # TurnstileGate (scan-submit human-verification modal — native <dialog>)
│   │                 # ProofOfTestsTable (I-5.6 Report-tab proof-of-tests; reuses .chk-* grammar),
│   │                 #   VerifyWaitlistTile, RightOfReplyForm (I-5.6 Agent Report lifecycle)
│   │                 # OwaspFindingGroup, ScoreMathTable, RemediationTerminal, RedactedTranscript,
│   │                 #   ComponentScoresTable (I-5.6 Phase B — Findings/Component tabs)
│   └── organisms/    # (composition shells if needed)
├── styles/
│   ├── tokens.css    # Token SSOT + dark-mode block + Tailwind v4 @theme
│   ├── components.css  # Page-vocabulary CSS (hex masks, page-head, ridges, nav-pill, score language, footer chrome) — ported from mockup
│   └── globals.css   # Tailwind v4 import + tokens + components + @fontsource imports + @layer base + .t-* typography
├── .ladle/           # Ladle story-browser config + global Provider that imports globals.css + Vite Tailwind plugin
└── stories/          # Ladle stories — one per component
webapp/src/components/  # Page-specific compositions (consume ui/)
webapp/src/styles/      # reset.css only (page-vocab CSS lives in ui/styles/components.css now)
```

- **Reusable components → `ui/`.** If a component is used on more than one page, lift it.
- **Page-specific components → `webapp/src/components/`.** Compositions of `ui/` primitives that only one route renders.
- **`ui/` never imports from `webapp/`.** One-way dependency — `webapp/` consumes `ui/`.

### CSS ownership — the one-way rule applies to CSS too

The dependency must be one-way for **stylesheets**, not just imports. A `ui/` component whose CSS physically lives in a `webapp/` page file is an inverted dependency — the component renders unstyled in Ladle (which loads `ui/styles/`, not page CSS) and the page silently owns DS chrome.

- **Any class rendered by a `ui/` component lives in `ui/styles/components.css`** — never in `webapp/src/styles/page-*.css`. (`components.css` is loaded on every page via `global.css → @ui/styles/globals.css → components.css`, and by Ladle — so DS component CSS there renders everywhere, including stories.)
- A **page-specific composition** that only one route renders keeps its CSS in that route's `page-*.css`.
- Decision tree when adding/moving a CSS block:
  - *Rendered by a `ui/` component, or reused across pages?* → `ui/styles/components.css`.
  - *Single-page layout / decorative band / one-off composition?* → that page's `page-*.css`.
- A page **may** override a DS component's appearance for one route (e.g. the homepage's taller `.ridge-pixel`). That override is a legitimate single-page rule and stays in `page-*.css` — it does **not** mean the base CSS belongs there.
- Custom properties consumed by a `ui/` component (e.g. the terminal `--t-*` palette) must be **re-rooted onto the component** in `components.css`, not left scoped to a page ancestor.

### CSS token discipline

Enforced by `scripts/check-css.cjs` (CI `validate` lane + a `repo: local` pre-commit hook):

- **(b) No `var(--token, #hex)` fallback literals** (repo-wide, `ui/styles/**` + `webapp/src/styles/**`). Tokens are always defined in `tokens.css`; a stale hex fallback never renders but lies about the real color and masks dark-mode bugs.
- **(c) No references to undefined custom properties** (repo-wide). Catches typos like the historical `--bg-paper` (→ `--bg-surface`), `--ink` (→ `--color-ink`), `--bg-dotgrid-ink` (→ `--bg-dot-grid`).
- **(a) No bare raw `#rrggbb`** in the cleaned shell page files (`page-catalog` / `page-scan-progress` / `page-scan-report` / `page-scan-submit`) — token-only. `#000`/`#fff` inside `mask`/`url()` compositing are exempt. The ported `page-home.css` (intentional mockup raw-hex) and `components.css` (intentional terminal-ANSI palette) are out of rule (a) scope.

## Hex-button vocabulary

The signature button silhouette is a chamfered hexagonal cap shape rendered via `-webkit-mask` + `mask` CSS. The mask SVG data lives in `ui/styles/tokens.css` as `--mask-hex-cap-left/-right`, `--mask-hex-notch-left/-right`, `--mask-half-cap-left/-right`.

- **`Button`** — 4 variants (`default`, `primary`, `paper`, `dark`, `ghost`) × 3 sizes (`sm`, `md`, `lg`). Mobile (<640px) drops the hex mask for legibility.
- **`ButtonPair`** — two adjacent `Button`s with the right cap of #1 chamfered + left cap of #2 notched.
- **`Chip`** — 24px h, 10px caps, mono font 11px — filter tags + scan-tier labels.
- **`Badge`** — 28px h, 12px caps, mono uppercase 700 — status flags ("LIVE", "INDEXED").
- **`GhStar`** — GitHub star CTA, paired half-cap segments.

### Brutalist offset shadows — never on buttons OR overlays/modals

The brutalist offset "stamp" shadow (`box-shadow: 4px 4px 0 …`, i.e. `--shadow-stamp`) is **banned on every interactive surface**:

- **Buttons** and any link/control styled as a button (e.g. `.rescan-btn`, `.pkg-gh`) **never** use it on hover (no `box-shadow: 4px 4px 0 …` + `transform: translate(-1px,-1px)`). Hover state reuses the DS `Button` language: a **background fill** change (e.g. ink→paper, or `primary`→`primary-dark`) plus at most a `translateY(-1px)` lift. No box-shadow, no diagonal nudge.
- **Overlays / modals** (`.turnstile-gate`, `.confirm-dialog`, any `<dialog>` chrome) **never** use the offset stamp either — an interactive overlay stamped like a sticker reads as a card, not a floating surface. Modals float on a **1px hairline border + the soft `--shadow-overlay` ambient lift over a dimmed, blurred `::backdrop`** (`backdrop-filter: blur(3px)`). That ambient lift is the one sanctioned drop-shadow exception, and it is subtle (large blur, negative spread, low opacity) — never the hard 4px offset.

`--shadow-stamp` is reserved for **non-interactive emphasis on cards/featured items** (e.g. `.rule-card:target`), used sparingly — never on a button or an overlay. (`--shadow-stamp-brand` was removed; it had no remaining sanctioned use.)

## Dual-mode scan controls (I-3.5)

Three DS components back the dual-mode `/scan` + homepage upload affordance. All CSS is DS-owned in `ui/styles/components.css`; new interactive tokens (`--toggle-*`, `--focus-ring`) live in `ui/styles/tokens.css`.

- **`SegmentedTabs`** (atom) — accessible roving-tabindex tablist (←/→/Home/End move, Enter/Space activate). Two variants: `underline` (the `.sk-tabs/.sk-tab` look — now DS-owned, see below) and `segmented` (the boxed `.seg/.seg-tab` control with a per-tab `teal`/`orange` active accent). Pair a tabpanel's `id` with `panelId(idBase, tabId)`.
- **`Toggle`** (atom) — self-contained `role="switch"` (no Radix). Teal track ON, `tone="orange"` for URL/repo mode, `compact` for the homepage. Thumb slides on `transform` (reduced-motion → instant).
- **`DropZone`** (molecule) — drag-and-drop + click-to-browse **multi-file** upload affordance built on a `<label>` + `<input multiple>` (no nested-interactive). Reports the picked `File[]` via `onFilesSelected`; the parent owns the accumulated list (`selectedFiles`) + `onRemove(index)` — append/remove semantics live in `useUploadFlow`. Controlled by a `state` prop driving the **`D-UP-ANIM`** 5-state machine (`idle → dragover → selected → uploading → error`): the zone **collapses** to glyph + sentence once files are picked (the `.dz-sub` sub-line collapses via the grid-rows `1fr → 0fr` + `overflow:hidden` + opacity technique, plus reduced zone padding/gap), file cards stamp-in (staggered ~50ms when several land at once), and uploading shows **one** aggregate teal scan-line sweep + `scaleX` progress bar under the list. **Transform/opacity only — the collapse is the sanctioned size-changing exception to that rule, and every state (incl. the collapse: grid-rows/padding snap, cards fade only) has a `prefers-reduced-motion: reduce` short-circuit** (`.dropzone--*` CSS). `compact` variant for the homepage panel.

The `.sk-tabs/.sk-tab/.t-ct` CSS was **moved** from `webapp/src/styles/page-item.css` into `ui/styles/components.css` (CSS-ownership rule) when `ItemTabs` adopted `SegmentedTabs variant="underline"` — `/items/<slug>` renders byte-identical.

## Capability/item report molecules (audit extraction)

`ItemTabs` (item-detail report) and `CapabilityReportTabs` (single-capability upload report) previously hand-rolled the same score table, checklist, and source viewer, with all CSS living only in `webapp/src/styles/page-item.css` (which the scan pages imported cross-page). Three shared molecules now own that vocabulary in `ui/`, with their CSS in `ui/styles/components.css` (§ Capability/Item report vocabulary):

- **`ScoreBreakdownTable`** — the `.score-cats` weight/score/contribution table. Pure render from `categories` + `subScores`; owns the `sk-bar-grow` bar-growth entrance.
- **`MarkdownSourceViewer`** — the `.md-*` macOS-chrome source viewer with the Rendered/Raw toggle + copy. Renderer-agnostic: the caller passes pre-rendered markdown as `renderedHtml: ReactNode` (`renderMarkdown` stays in `webapp/` — `ui/` must not import a markdown renderer).
- **`CheckGroupList`** — the `.chk-*` grouped pass/warn/fail checklist (`score × empty-category` copy via `emptyScanNoun`).

### Explainable findings — `FindingDetail` is the shared flagged-finding card

The v3 mockups (`SaferSkills-Scan-Results-{Private,File}-v3`) ratified **consolidating** the flagged-finding presentation into one shared molecule, **superseding** the earlier "FindingRow vs CheckGroupList — do NOT consolidate" rule (and retiring `FindingRow` + its container `SubScoreAccordion`, both now removed).

- **`FindingDetail`** (`ui/components/molecules/FindingDetail.tsx`, the `.find-card`) is THE flagged-finding card on **every** scan surface — the repo scan cap-bodies (`ScanReportView`) and the per-capability checklist (`CheckGroupList`'s flagged-category slot). It is a native `<details>` whose collapsed summary (severity pill · plain-English title · `rule_id · category · file` meta · `×N` count) expands to: severity rationale → why-it-matters → the matched-line excerpt (line gutter, hit line, **revealed invisibles**) → occurrences → how-to-fix (action · steps · Avoid→Safer) → a collapsed trace footer (rule link · sha256 copy · rubric · GitHub). It is **fully presentational** — the webapp (`FindingExplanation`) composes it from the generated `RULE_CONTENT` map + the backend `evidence_excerpt`; `ui/` never imports the map (`webapp/src/lib/findings/explain.ts` does the grouping + lookup + interpolation).
- **`CheckGroupList`** keeps only its **shell**: one `.chk-group` per score axis with a green "all checks passed" row for empty categories. Flagged categories render `FindingDetail` cards via the `renderCategoryFindings` slot the webapp supplies (kept as a slot so `ui/` stays map-free). Without the slot (Ladle / standalone) the compact `CheckRow` warn/fail row is the fallback.

**Dedup**: one card per `(rule_id, file_path)` — occurrences collapse to a count + locations list (`groupFindings`).

**Severity pill deviation**: the 5-tier `.sev`/`.sw` pill is **not** `BandPill`. `BandPill` is **tier**-colored (4 bands g/y/o/r) and cannot express the 5-tier **severity** palette — notably `info`=blue and `high`=solid fill. It is now extracted into the `SeverityPill` atom (`ui/components/atoms/SeverityPill.tsx`, defining its own `Severity` union), rendered by **both** `FindingDetail` and the public `/methodology` RuleCard (Astro renders it to static HTML — no `client:` directive). The `.sev`/`.sw` CSS stays with the `.find-card` vocabulary in `components.css` (byte-identical output).

### `.fc-*` / `.ex` / `.ic` / `.sp` CSS vocabulary (DS-owned)

All `FindingDetail` CSS lives in `ui/styles/components.css` (the one-way CSS-ownership rule): `.find-cards` (container) + `.find-card`/`.fc-*` (card chrome), `.sev`/`.sw` (severity pill), `.ex`/`.ex-line`/`.ln`/`.code`/`.ex-elide` (the always-dark code excerpt — a terminal surface, token + intentional `#fff`, per the components.css terminal-palette exemption to rule (a)), `.ic.{zw,bidi,homo,space}` (revealed invisible-char chips), `.fc-occ-*` (occurrences), `.fc-fix`/`.fc-safer`/`.sp` (remediation + Avoid→Safer), `.fc-trace*` (footer). **Framework reference badges** (`.fw-badges`/`.fw-badge` + the `.owasp-llm`/`.mitre-atlas`/`.cwe` family tints) are also DS-owned in `components.css`, rendered through the shared `FrameworkBadges` atom by **both** `FindingDetail` (the `.fc-frameworks` block) and the `/methodology` RuleCard — so the markup + family-label maps live once and the one-way CSS rule keeps them out of any page stylesheet. The native `<details>` collapse + the chevron rotation are the only motion — **reduced-motion guarded** (`@media (prefers-reduced-motion: reduce)`). `ui/lib/reveal-invisible.ts` (pure) classifies codepoints into the four `.ic` buckets; the component renders each segment as escaped React text / a labelled chip — **never innerHTML**, so verbatim scanned bytes (incl. a `{match}` placeholder value) cannot inject markup.

### `.cap-filter` is a filter group, NOT `SegmentedTabs`

The repo scan report's capability type-filter (`.cap-filter`/`.cf`/`.ct` in `ScanReportView`) is intentionally a `role="group"` of toggle buttons, **not** a `SegmentedTabs` (`role="tablist"`). It filters one results region (`.cap-list`) — "All / Skill / MCP / …" all render the same table with a filtered subset, and "All" is a superset, not a peer tab. There are no per-option `tabpanel`s to wire, so a tablist would misrepresent the semantics to assistive tech. It is also a page-specific composition (rendered by the webapp-side `ScanReportView`), so its CSS correctly stays in `webapp/src/styles/page-scan-report.css` (not `components.css`). A future pass should leave it as-is — adopting `SegmentedTabs` here was evaluated and declined.

### `.mf-*` file-tab strip is a page-specific tablist (I-3.5)

The multi-file upload report's file-tab strip (`.mf-nav`/`.mf-tabs`/`.mf-tab`/`.mf-glyph`/`.mf-dot`/`.mf-score` in `FileTabStrip`) is a genuine `role="tablist"` (one tab per scanned file, each swapping the per-file `tabpanel` body in `UploadReport`). It is **not** `SegmentedTabs` because each tab renders rich, non-label content — a kind glyph + filename + tier dot + tier-colored score — that `SegmentedTabs`' label-only API can't express; it mirrors `SegmentedTabs`' roving-tabindex keyboard model (←/→/↑/↓/Home/End, automatic activation) by hand. Like `.cap-filter`, it is a page-specific composition (rendered by webapp-side `FileTabStrip`/`UploadReport`), so its CSS lives in `webapp/src/styles/page-scan-report.css` (token-only, both themes, reduced-motion guarded) — **not** `components.css`. A future "lift to a DS tablist" pass should extend `SegmentedTabs` with a render-slot before merging, or leave this as-is.

### Agent Report vocabulary (I-5.6)

The Agent Report (`/agents/[id]` + `/agents/r/[token]`) is a **token-only sibling** of the scan report — it introduces zero new design language and reuses `page-scan-report.css`'s `.sr-stat-band`/`.sr-stat-grid`/`.score-cell`/`.sr-facts`/`.sr-head-row`/`.sr-head-meta`/`.sr-big`/`.manage-bar`/`.mbtn` (the public route imports `page-scan-report.css` ahead of `page-agent-report.css`).

- **DS-component CSS lives in `ui/styles/components.css`** (the one-way CSS-ownership rule): every class rendered by a `ui/` agent component — `.ar-verb`/`.vb-sep` (`AgentVerb`), `.trust-pill`/`.ti`/`.tip` (`TrustTierPill`), `.cap-reason`/`.cr-ic` (`CapCallout`), `.ar-tests`/`.ar-tests-head`/`.tt-*` + the `.chk-gobtn`/`.chk-row.fail` **additions scoped under `.ar-tests`** so the shared scan-report `CheckGroupList` is untouched (`ProofOfTestsTable`), `.evidence-public-note` (`EvidenceWithheldNote`), `.ar-stale-banner` (`StalePackBanner`), `.vw-*` (`VerifyWaitlistTile`), `.ror-*` (`RightOfReplyForm`). **Phase B (I-5.6) adds**: `.owasp-group*`/`.og-*` (`OwaspFindingGroup`), `.ref-chip`/`.fc-refs` (`RefChip` + the per-finding refs row), `.score-math`/`.sm-*` (`ScoreMathTable`), `.ar-remediation`/`.ar-rem-*`/`.ar-fix-snippet`/`.ar-term`/`.at-*` (`RemediationTerminal`), `.transcript`/`.ts-*` + `.transcript .ex-line.canary` (`RedactedTranscript`, reusing the dark `.ex` line-window), `.ar-components-tab`/`.cs-*` (`ComponentScoresTable`), `.prov-chip`/`.ar-prov-chips` (`ProvenanceChips`). Ported from the locked mockup with `body.va.dark → html.dark`, tokens only, reduced-motion guards on every transition; the `.ex`/`.ar-term`/`.transcript` terminal surfaces use the sanctioned components.css terminal palette (intentional `#fff`/diff hex).
- **`webapp/src/styles/page-agent-report.css`** owns ONLY page-composition glue (`.ar-scoreline` hero row, `.ar-panel`/`.ar-panel-lead` tab panels, `.ar-tab-placeholder`, `.ar-lifecycle`, the Phase-B `.ar-findings-head`/`.ev-cap`/`.ar-export-fixes` Findings-tab header + the `.ar-badge-band`/`.ar-badge-grid`/`.ar-badge-l`/`.ar-badge-r`/`.ar-prov-row` badge-band layout that wraps `EmbedBadgeBox` + `ProvenanceChips`) — it is a **`check-css` SHELL file** (registered in `scripts/check-css.cjs::SHELL_FILES`; token-only, no raw hex). The `--brand-primary-light` semantic alias the report references is defined once in `tokens.css` (`var(--ol-brand-primary-light)`, D-5.6-16).
- The report body is the React island `webapp/src/components/agent/AgentReport.tsx` (page-specific composition), mounted `client:load` (SSR'd + hydrated); the Findings tab + badge band are sub-compositions `webapp/src/components/agent/AgentFindings.tsx` + `AgentBadgeBand.tsx`, with the pure DTO→view mapping (ref deep-links, OWASP grouping, score-math ledger) in `webapp/src/lib/agent/findings-view.ts`. Telemetry (`agent_report_*`) + the manage/verify/reply fetches + the client-side Markdown export (`webapp/src/lib/agent-report-markdown.ts`, full report + remediation checklist) live in the island; the `ui/` molecules stay presentational (callback props). The Findings card body reuses the DS `.find-card` chrome but composes the agent-specific body (refs → score-math → route-driven evidence → terminal remediation) — `FindingDetail` itself is not reused (its repo-scan body shape — occurrences/sha/github/reveal-invisibles — does not fit the behavioral finding). The **agent `EmbedBadgeBox` variant** (`kind="agent"`) emits `/badge/agent/{id}/{score}.svg` + `/agents/{id}` (D-5.6-14, Codex P2).

## Page-head pattern

Every in-app page (catalog / scan / report / item / about / docs / methodology) starts with a `<PageHead>` strip. Props: `eyebrow`, `title`, `lede?`, `className?`. CSS lives in `ui/styles/components.css::.page-head`. Includes the 12px tick-ruler accent at top, the 40×40 plus-grid background, `<mark>` highlight option, and an orange `<span class="script">` accent option. The `<mark>` highlight (driven by `--brand-highlight`) is **theme-aware**: pale teal tint on light paper, deep teal (`--ol-brand-primary-dark`) in dark mode — the same treatment as the homepage hero rotator (`--color-citron`), so every highlighted title reads identically across pages and modes.

On every non-homepage page a `<PageRidge>` is placed **directly under** the `<PageHead>` — it provides the header→body transition (replacing the old flat `1px solid ink` border) and carries the page-path cue in its centered label. See "Header ridges" below. (Metadata pills were removed; a future data-heavy page that needs page-level metadata reintroduces a dedicated component then — per scope discipline.)

## Ridge dividers

### Inter-section ridges

Four variants, between content sections:

- **`RidgeStars`** — paper-deep bg with plus-grid pattern overlay; 72px tall.
- **`RidgeFlow`** — gradient transition between sections (paper-deep → paper); 88px tall.
- **`RidgePixel`** — dark-slate bg with the orange tick-ruler accent; 64px tall (used as transition INTO dark sections).
- **`RidgeRuler`** — the quiet one: a 48px paper-deep band carrying only a centered tick ruler (orange majors + faint minors), no fill or hatch. Pure-CSS (no SVG), theme-aware (reads light-on-light and dark-on-dark). A discrete "ruler" seam — e.g. directly under the `/scan` PageHead.

Each carries an optional centered uppercase mono label.

### Header ridges (`PageRidge`)

A separate, taller family (~104–116px) that carries the header→body transition under `<PageHead>`. One distinct `variant` per non-homepage page; all three recombine the same brand cues (contour + plus-grid + wave + tick-ruler) so pages feel unique-but-familiar:

- **`contour`** (`/about`) — topographic contour bundle dissolving toward the content, with a thin tick-ruler edge.
- **`mesh`** (`/methodology`) — a plus-grid field crossed by a dashed alignment seam + scattered teal/orange `+` marks.
- **`swell`** (`/docs`) — a smooth wave bundle with corner registration crosshairs.

Mark colors are token-driven (`--brand-primary` / `--brand-accent` / `--color-ink` via the `.rdg-s-*` classes in `components.css`), so every stroke flips for dark mode for free. Pass `label` for the centered page-path cue (e.g. `label="— /ABOUT —"`). Adding a new page = a new `variant` here + the CSS height/treatment + a Ladle story case.

## Section surfaces

Non-homepage content sections use the shared `.page-section` surface (`ui/styles/components.css`) in an **alternating rhythm**, section to section:

- **`.page-section--grid`** — ruled blueprint grid (60px lines) + a `+` cross at every intersection — the homepage install-band texture, recolored gray-on-light / faint-on-dark.
- **`.page-section--flat`** — a simpler dot grid (26px) on a slightly deeper `--color-paper-deep` band (dark: `--bg-page-alt`).

Both are theme-aware (slate-50 → slate-900 grid, slate-100 → slate-800 flat). The surface owns the section background + vertical padding; page-specific CSS keeps only inner-component typography/layout. **Verify cards on `--flat` bands read correctly in dark mode** — a card whose dark background equals `--bg-page-alt` (slate-800) blends into a flat band; recess it to `--color-paper` (slate-900) or lift it to `--bg-surface-mute` (slate-700). See the `.rule-card` override in `page-methodology.css` for the canonical example.

### Non-homepage page template

`NavBar → PageHead → PageRidge → alternating .page-section bands (with RidgeStars/RidgeFlow between) → CtaBand → Footer`. Every new non-homepage page inherits this template so brand DNA stays consistent.

## Scrolled-pill nav

**`NavBar` is the single top bar — every page mounts `<NavBar>`; never hand-roll another top bar.** The `GhStar` GitHub-star CTA is a **permanent, non-optional** part of NavBar — rendered unconditionally, never gated on the count. `ghCount` is only an SSR placeholder; when a route omits it the chip renders empty and the site-wide `NavStars` island (mounted in `Base.astro`) fills it live. Do **not** reintroduce a `ghCount > 0` guard or otherwise make the GhStar conditional — that was the regression that dropped it from `/items/<slug>` + `/respond`. Covered by `NavBar.test.tsx` ("always renders the GhStar even with no ghCount").

`NavBar` morphs on scroll: transparent + full-width when `scrollY < 24`, then constrains to `max-width: 1100px`, gains `backdrop-filter: blur(12px)`, hairline border, soft shadow, and 4 corner registration marks (`+` crosshairs). Implemented via passive `scroll` listener throttled to `requestAnimationFrame`. Corner marks hidden below 980px. Reduced-motion: no morph transition.

**Mobile collapse (≤860px).** Below 860px — the width at which the horizontal row (wordmark + 5 links + GhStar + scan CTA) no longer fits — the desktop links (`.nav-links`) and right cluster (`.nav-right`) are hidden and a squared, 0-radius, hairline **hamburger button** (`.nav-toggle`) is shown instead. Tapping it opens a slide-down drawer (`.nav-drawer`, absolutely positioned under the bar, `--color-paper` / `--color-line` / `--shadow-hairline`, blurred like the scrolled pill) holding all 5 links + GhStar + the "Scan a capability" CTA stacked. State lives in the `NavBar` island (`useState`); the drawer closes on link click and on `Escape`, carries the `hidden` attribute when closed (so it contributes zero width and stays out of the a11y tree), and its bar-to-X morph sits under the reduced-motion guard. **Active-link state is SSR-correct**: each route passes `activePath={Astro.url.pathname}` to `NavBar` and `aria-current` is derived from that prop — never from `window.location` during render (which caused a hydration mismatch). `≥861px` is byte-for-byte unchanged (`.nav-toggle` / `.nav-drawer` are `display:none`).

## Theme classes — `<html class="dark">`

Tailwind v4 dark mode uses `@custom-variant dark (&:where(.dark, .dark *));` in `ui/styles/tokens.css`. Theme application: `<html class={initialClass}>` set inline by a FOUC-prevention `<script is:inline>` in `webapp/src/layouts/Base.astro` `<head>`. `ThemeToggle` is a 3-state pill (Light / Dark / Auto) writing `localStorage['ss-theme']`. Auto follows `prefers-color-scheme` live. View transitions re-apply theme on `astro:after-swap`.

## Astro + React 19 islands

- Components in `ui/components/*.tsx` are **plain React 19** — no Astro APIs.
- `.astro` shells in `ui/components/atoms/{Wordmark,Logo,Footer}.astro` are framework-agnostic — no React imports beyond optional hydration of child islands.
- Astro routes hydrate components via `client:` directives. Default to `client:visible` for below-the-fold; `client:idle` for above-the-fold non-interactive; `client:load` only when interactivity is needed immediately.
- **Never `client:only`** unless an SSR pass fails — static HTML is the SEO + performance baseline.

## Story + test + accessibility

Every component under `ui/components/` ships with:

1. **Ladle story** in `ui/stories/<kind>/<Component>.tsx` — visual review. Astro shells get a React mirror story that replicates the static HTML.
2. **Vitest test** in `ui/test/components/<kind>/<Component>.test.tsx` — at least one render + one interaction case (React `.tsx` only; Astro shells are covered by Ladle build).
3. **vitest-axe smoke** — basic a11y violations gate.

The CI `ladle-build` lane catches broken stories; `test-fe` runs the vitest suite. Missing any of the three blocks merge.

## Visual-validation loop (local-only)

Every page route is pixel-diffed against the matching `.local/.brainstorms/frontend/mockup-shots/*.png` reference at 1440×900, 1920×1080, 375×812. Tool: `tools/visual-diff/` (Phase A2+ — deferred from A1). Thresholds: <0.5% per component, <1% per page. No iteration cap. **Local-only — not a CI lane** (mockup baselines are gitignored under `.local/`). PR descriptions record final diff ratios; founder ratifies via outbox `02-designer-handoff-final-pass.md`.

## Anti-recommendation rule

SaferSkills is an **independent public service**. Catalog content — scan-result pages, methodology docs, README hero copy, error messages — **never recommends OpenLatch or any other commercial product**. The brand voice is neutral, technical, and self-contained.

- Footer attribution: "An OpenLatch project" — the only catalog surface that names OpenLatch.
- About-page disclosure: the only SaferSkills-domain page that names OpenLatch as steward.
- Catalog item pages, methodology page, rule pages, scan-report pages MUST NOT cross-link to OpenLatch products.
- Email risk-alerts (I-06) get a single closing line about OpenLatch's runtime enforcement — the lone exception.
- **Outbound email From: `notifications.openlatch.ai`** — single Resend verified sending domain shared with OpenLatch (cost decision 2026-05-28). Display name is `SaferSkills`; reply-to is `@openlatch.ai`. Disclosed on `/about` and `/privacy`. This is the third disclosed shared-stewardship surface (alongside footer + About-page disclosure).

Enforced in code review on every PR that adds catalog content. Violations are a brand-policy regression, not a style suggestion.

## Hard rules

1. **Tokens, not literals.** Never write `#0D9488` or `rounded-md` in a component — reference `var(--brand-primary)` / `rounded-none`.
2. **0 radius, 1px borders, no drop shadows.** `--radius-0` is the default. `--radius-xs` for form fields/chips. `--radius-pill` for badges only. Shadows replaced by `--shadow-hairline` + `--shadow-stamp` (used sparingly on **non-interactive** cards — **never** an offset/brutalist shadow on a button **or an overlay/modal**; see § Brutalist offset shadows). The lone drop-shadow exception is `--shadow-overlay`, the soft ambient lift for floating modals.
3. **`ui/` is framework-agnostic.** No Astro imports in React components. No `import.meta.env` access in component code (read env in the route, pass via props).
4. **Story + test + axe** for every shared React component; Astro shells need story + Ladle build pass only.
5. **Anti-recommendation** — catalog never cross-promotes.
6. **No CDN-hosted fonts** — `@fontsource/*` or self-hosted woff2 only. CI greps for `fonts.googleapis.com`.

## When to update this rule

| Change | Updates here |
|---|---|
| New token added to `ui/styles/tokens.css` | Tokens table |
| New component category | "Component layout" |
| Astro hydration strategy change | "Astro + React 19 islands" — also see `frontend-patterns.md` |
| Brand-posture exception (cross-link approved) | "Anti-recommendation" — get a brand sign-off first |
| New inter-section ridge variant | "Ridge dividers" § Inter-section ridges |
| New `PageRidge` (header ridge) variant | "Ridge dividers" § Header ridges + the new page's `variant` |
| New section-surface class / alternation rule | "Section surfaces" |
| New hex-button variant or size | "Hex-button vocabulary" |
| New visual-diff CLI flag | "Visual-validation loop" |
| New DS-component CSS / relocation | "CSS ownership" — keep the one-way rule (component CSS in `ui/styles/`) |
| New `check-css.cjs` rule / scope change | "CSS token discipline" + `scripts/check-css.cjs` + `ci-cd.md` (validate lane) |
| New runtime-set CSS custom property | `scripts/check-css.cjs` `RUNTIME_VARS` allowlist |
