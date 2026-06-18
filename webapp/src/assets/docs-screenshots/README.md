<div align="center">

<a href="../../../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Docs screenshots</h3>
<p>Theme-aware product screenshots embedded in the native docs.</p>

</div>

## What it is

The `*.{light,dark}.png` pairs here are the product screenshots embedded in the docs via the `Screenshot.astro` component (`webapp/src/components/docs/Screenshot.astro`), which shows the one matching the reader's theme. They are **generated, never hand-edited** — regenerate them so they never go stale.

## Regenerate

One command captures every surface in both themes:

```bash
# Default target = staging (the durable public refresh target):
pnpm --filter @saferskills/webapp capture:screenshots

# Override the target (e.g. a local rich-data stack, before staging is scanned):
SAFERSKILLS_SCREENSHOT_BASE=http://127.0.0.1:4399 \
  pnpm --filter @saferskills/webapp capture:screenshots
```

The harness (`webapp/scripts/capture-docs-screenshots.mjs`) resolves a representative item slug / scan-run id / agent-run id from the live API at run time, so the report shots survive data changes. A surface whose data isn't present on the target is **skipped with a logged note** rather than emitting a broken shot — re-run against a deployment that has scored items + agent scans to fill those in.

## Surfaces

| File base | Surface | Embedded on |
|---|---|---|
| `homepage` | `/` | `getting-started/what-is-saferskills` |
| `catalog` | `/capabilities` | `find-and-verify/browse-the-catalog` |
| `scan-form` | `/scan` | `find-and-verify/scan-a-repo` |
| `scan-report` | `/scans/<id>` | `find-and-verify/read-a-scan-report` |
| `item-report` | `/items/<slug>` | `find-and-verify/read-a-scan-report` |
| `agent-report` | `/agents/<id>` | `agent-scan/read-an-agent-report` |
| `agent-directory` | `/agents` | `agent-scan/what-agent-scan-is` |

## Notes

- **Not a CI lane.** Capture needs a running deployment and is slow; it is an on-demand refresh. The `docs-build` (frontmatter) + `lighthouse-a11y` (docs axe + link check) lanes gate the docs — every embed carries descriptive `alt` text to stay axe-clean.
- The initial committed set was captured against a local stack with seeded scan data (staging had ingested-but-unscored items at the time). Staging is the refresh target once it carries scan + agent-scan results.
- Captured at a pinned 1440×900 viewport, `deviceScaleFactor: 2`. Served via the Sharp-free passthrough image service (the build runs on Alpine), so the PNGs ship as-is — keep them reasonably sized.

---

<sub>Part of **[SaferSkills](../../../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
