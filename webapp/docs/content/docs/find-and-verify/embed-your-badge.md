---
title: "Embed Your Badge"
description: "Copy a Markdown or HTML badge that shows your live SaferSkills score and links back to the public report."
updated: 2026-06-16
---
Every scanned capability gets a live trust badge — an SVG showing its current SaferSkills score that re-renders on each re-scan. Embed it in your project's README so anyone who finds your capability sees an independent score before they install anything. The badge links straight to the public report, where they can read every rule that fired and your vendor response. Copy the exact snippet from your capability's report page.

## How do I add the badge to my README?

Paste this Markdown into your README, substituting your capability's scan id, score, and slug:

```markdown
[![SaferSkills 92/100](https://saferskills.ai/badge/<scan_id>/<score>.svg)](https://saferskills.ai/items/<slug>)
```

The image is the badge SVG at `https://saferskills.ai/badge/<scan_id>/<score>.svg`; the link wraps it to your full public report at `https://saferskills.ai/items/<slug>`. The easiest way to get the exact snippet for your capability — already filled in with your real ids — is the **Copy to MD** button on your report page at `saferskills.ai/items/<slug>`.

If your README is HTML rather than Markdown, wrap the same image and link with `<a>` and `<img>` tags pointing at the same two URLs.

## What does the badge show?

The badge renders your capability's aggregate score out of 100. The score maps to a color band — green (80–100, Approved), yellow (60–79, Watch), orange (40–59, Caution), or red (0–39, Block). Because the badge is generated from the score in the URL and re-rendered on every re-scan, it stays current: when your capability is re-scanned and the score changes, the badge updates with it. The report it links to carries the full picture — the five sub-scores, every finding with its `rule_id` and evidence, and any vendor right-of-reply.

## Why embed the badge?

The badge is the distribution flywheel for a verified capability. An installer who lands on your README sees an independent, methodology-backed score *before* they run anything — the safe path becomes the visible path. A strong, public score is a credible trust signal you did not have to assert yourself; SaferSkills computed it deterministically and anyone can re-derive it. And every badge view is a link back to the public report, so the methodology travels with your capability wherever its README is read.

## How do I get a score to badge in the first place?

Your capability needs a public report. If it is already in the catalog, open its page and copy the badge snippet. If it is not yet scanned, submit it — see [scan a repo](/docs/find-and-verify/scan-a-repo/) to run a scan from your GitHub URL. For the full author workflow — getting scanned, claiming your repo, and keeping your score current — see [publish and get scanned](/docs/for-authors/publish-and-get-scanned/).
