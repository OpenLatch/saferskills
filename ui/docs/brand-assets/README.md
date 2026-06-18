<div align="center">

<a href="../../../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../../../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Brand assets</h3>
<p>Canonical SaferSkills logo and wordmark files, with usage rules.</p>

</div>

> **Scope.** SaferSkills only. Do not mix with OpenLatch master-brand assets in the same lockup. The only OpenLatch acknowledgement on a SaferSkills surface is the `An OpenLatch project` footer attribution — see the [Brand Posture doc](https://github.com/openlatch/saferskills/blob/main/docs/brand-posture.md).

## Asset inventory

### Logo only (icon, no text)

| File | Use | Background | Size |
| ---- | --- | ---------- | ---- |
| `saferskills-logo.png` / `.svg` | Default. Color logo on any surface. | Transparent | 1024×1024 |
| `saferskills-light-logo.png` / `.svg` | Alias for default. Use on light surfaces. | Transparent | 1024×1024 |
| `saferskills-logo-bw.png` / `.svg` | Monochrome (slate-900 silhouette). Print, single-color contexts, partner badges. | Transparent | 1024×1024 |
| `saferskills-logo-social.png` / `.svg` | Open Graph / social preview image. | White | 1200×630 |

### Wordmark (logo + "SaferSkills" text)

| File | Use | Background | Text color | Size |
| ---- | --- | ---------- | ---------- | ---- |
| `saferskills-wordmark.png` / `.svg` | Default canonical lockup. Light surfaces. | White | Slate-900 `#0F172A` | 1600×400 |
| `saferskills-light-wordmark.png` / `.svg` | Alias for default. | White | Slate-900 `#0F172A` | 1600×400 |
| `saferskills-colored-light-wordmark.png` / `.svg` | Alias for default. The "colored" part is the logo, not the text — the SaferSkills brand spec forbids colored wordmark text. | White | Slate-900 `#0F172A` | 1600×400 |
| `saferskills-dark-wordmark.png` / `.svg` | Dark mode. App console, dark hero, dark partner badges. | Slate-900 `#0F172A` | White `#FFFFFF` | 1600×400 |

### Animated

| File | Use |
| ---- | --- |
| `saferskills-logo-animated.mp4` | Animated logo loop (4s, 1:1 aspect, 720p H.264 ~155 kbps, silent). Use for primary hero, branded video intros. Do NOT use for favicon, README badge, or any inline context where motion distracts. Loops seamlessly. |

## Canonical brand-system tokens

| Token | Value |
| ----- | ----- |
| **Logo body color** (lighter teal) | `#0D9488` |
| **Logo counter color** (darker teal) | `#0F766E` |
| **Wordmark — light bg** | Slate-900 `#0F172A` |
| **Wordmark — dark bg** | White `#FFFFFF` |
| **Wordmark typeface** | Onest |
| **Wordmark weight** | SemiBold 600 |
| **Wordmark tracking** | -0.02em |
| **Wordmark case** | camelCase — `SaferSkills` |
| **Logo-to-text gap** | 8px (tight, fixed at all sizes) |

## What's banned

- Coloring the wordmark text anything other than slate-900 (light surfaces) or white (dark surfaces). No teal text. No cobalt text. No gradient text.
- Using a typeface other than Onest SemiBold 600 for the wordmark.
- All-caps or all-lowercase rendering of the brand name. Always `SaferSkills`.
- Reducing the logo to a single color (other than the `-bw` variant). The two-tone teal IS the logo.
- Pairing the SaferSkills logo with the OpenLatch master logo as siblings (e.g. "powered by OpenLatch" with both logos shown). The only OpenLatch reference on a SaferSkills surface is the footer attribution text.
- Adding a tagline integrated into the wordmark lockup. The wordmark stands alone.
- Applying drop shadows, glows, gradients, or any non-flat effect.
- Rotating, skewing, or distorting either the logo or the wordmark.

## Technical notes on the SVG files

The `.svg` files in this folder are **PNG-derived rasters embedded inside an SVG container** (base64 `<image>` element). They are valid SVG files that render correctly at any size, but they will pixelate when zoomed significantly past the source PNG's native resolution.

**A true hand-redrawn vector master is on the design TODO list.** The angular geometry of the S would benefit from being redrawn in Illustrator/Figma with explicit path data so the logo scales infinitely without any rasterization. Until that is done, these SVG wrappers are functional but not optimal for ultra-high-resolution use (e.g. billboards, large print).

For now, **prefer PNG for any use case below 2× the source size, and refer to the `saferskills-logo-social.png` (1200×630) for OG / preview contexts.**

## Generation

These assets were produced by the SaferSkills brand-asset builder pipeline:

```
.local/logo-gen/build-brand-assets.py       # logo PNG variants (color, BW, social) via PIL
.local/logo-gen/brand-assets-builder.html   # wordmark layout via HTML+Onest, screenshotted by playwright
.local/logo-gen/build-brand-svgs.py         # SVG wrappers via base64-embed
```

To rebuild after editing the master logo or wordmark spec, re-run these in order.

## Related

- Canonical spec: `05-GTM/Launch/SaferSkills - Wordmark Spec.md` in the vault
- Project index: `03-Product/SaferSkills.md` in the vault
- Brand voice: `05-GTM/Launch/SaferSkills - Brand Posture.md` in the vault

---

<sub>Part of **[SaferSkills](../../../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
