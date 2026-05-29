type Variant = 'contour' | 'mesh' | 'swell'

interface Props {
  variant: Variant
  label?: string
  className?: string
}

/**
 * Header ridge family — the rich brand divider that sits directly under a
 * `<PageHead>` on every non-homepage page, replacing the old flat border.
 *
 * Each page gets its own `variant`; all three recombine the same brand cues
 * (topographic contour bundle + plus-grid field + wave bundle + tick-ruler)
 * so pages feel unique-but-familiar. Taller than the inter-section ridges
 * (`RidgeStars`/`RidgeFlow`/`RidgePixel`) since it carries the header→body
 * transition.
 *
 * - `contour` (/about)       — topographic contour bundle dissolving toward the
 *                              content, with a thin tick-ruler edge (CSS ::before).
 * - `mesh` (/methodology)    — a plus-grid field (CSS ::before) crossed by a
 *                              dashed alignment seam + scattered teal/orange `+`.
 * - `swell` (/docs)          — a smooth wave bundle with corner registration
 *                              crosshairs.
 *
 * Stroke/fill colors are driven by CSS classes mapped to tokens
 * (`--brand-primary` / `--brand-accent` / `--color-ink`) in
 * components.css::.ridge-header, so every mark themes for dark mode for free.
 * `aria-hidden` because it is purely decorative. Pure React 19 — no Astro APIs.
 */
export default function PageRidge({ variant, label, className = '' }: Props) {
  return (
    <div
      className={`ridge ridge-header ridge-${variant} ${className}`.trim()}
      aria-hidden="true"
    >
      {label && <span className="ridge-label">{label}</span>}
      {variant === 'contour' && <ContourSvg />}
      {variant === 'mesh' && <MeshSvg />}
      {variant === 'swell' && <SwellSvg />}
    </div>
  )
}

/** Smooth S-bend contour line spanning the full width at baseline `y`. */
function wave(y: number, amp: number): string {
  return `M0,${y} C140,${y - amp} 280,${y + amp} 420,${y} C560,${y - amp} 700,${y + amp} 840,${y} C980,${y - amp} 1120,${y + amp * 0.7} 1280,${y}`
}

/** A small `+` registration mark centred on (cx, cy) with arm half-length `r`. */
function Plus({ cx, cy, r = 6, cls }: { cx: number; cy: number; r?: number; cls: string }) {
  return (
    <g className={cls} strokeWidth={1.4} strokeLinecap="square">
      <line x1={cx} y1={cy - r} x2={cx} y2={cy + r} />
      <line x1={cx - r} y1={cy} x2={cx + r} y2={cy} />
    </g>
  )
}

function ContourSvg() {
  // Topo bundle: denser/brighter near the head, dissolving toward the body.
  const lines: Array<{ y: number; amp: number; cls: string; op: number; w?: number }> = [
    { y: 30, amp: 14, cls: 'rdg-s-teal', op: 0.3 },
    { y: 40, amp: 14, cls: 'rdg-s-ink', op: 0.22 },
    { y: 50, amp: 14, cls: 'rdg-s-orange', op: 0.45 },
    { y: 60, amp: 15, cls: 'rdg-s-teal', op: 0.6, w: 1.4 },
    { y: 72, amp: 13, cls: 'rdg-s-ink', op: 0.26 },
    { y: 84, amp: 13, cls: 'rdg-s-orange', op: 0.62, w: 1.4 },
    { y: 96, amp: 12, cls: 'rdg-s-teal', op: 0.32 },
    { y: 107, amp: 10, cls: 'rdg-s-ink', op: 0.13 },
  ]
  return (
    <svg viewBox="0 0 1280 116" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <g fill="none" strokeLinecap="round">
        {lines.map((l) => (
          <path
            key={l.y}
            className={l.cls}
            d={wave(l.y, l.amp)}
            strokeOpacity={l.op}
            strokeWidth={l.w ?? 1.2}
          />
        ))}
      </g>
      <g opacity={0.7}>
        <Plus cx={210} cy={20} r={5} cls="rdg-s-orange" />
        <Plus cx={900} cy={18} r={5} cls="rdg-s-teal" />
      </g>
    </svg>
  )
}

function MeshSvg() {
  return (
    <svg viewBox="0 0 1280 104" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <line
        className="rdg-s-ink"
        x1="0"
        y1="52"
        x2="1280"
        y2="52"
        strokeOpacity="0.3"
        strokeDasharray="4 7"
      />
      <line
        className="rdg-s-ink"
        x1="0"
        y1="90"
        x2="1280"
        y2="20"
        strokeOpacity="0.18"
        strokeDasharray="5 8"
      />
      <g opacity={0.85}>
        <Plus cx={160} cy={30} cls="rdg-s-teal" />
        <Plus cx={620} cy={70} cls="rdg-s-teal" />
        <Plus cx={1080} cy={34} cls="rdg-s-teal" />
        <Plus cx={380} cy={68} cls="rdg-s-orange" />
        <Plus cx={860} cy={28} cls="rdg-s-orange" />
        <Plus cx={1180} cy={72} cls="rdg-s-orange" />
      </g>
    </svg>
  )
}

function SwellSvg() {
  const lines: Array<{ y: number; amp: number; cls: string; op: number; w?: number }> = [
    { y: 40, amp: 16, cls: 'rdg-s-teal', op: 0.35 },
    { y: 52, amp: 16, cls: 'rdg-s-orange', op: 0.5 },
    { y: 64, amp: 16, cls: 'rdg-s-ink', op: 0.26 },
    { y: 76, amp: 16, cls: 'rdg-s-teal', op: 0.6, w: 1.4 },
    { y: 88, amp: 15, cls: 'rdg-s-orange', op: 0.65, w: 1.4 },
  ]
  return (
    <svg viewBox="0 0 1280 116" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <g fill="none" strokeLinecap="round">
        {lines.map((l) => (
          <path
            key={l.y}
            className={l.cls}
            d={wave(l.y, l.amp)}
            strokeOpacity={l.op}
            strokeWidth={l.w ?? 1.2}
          />
        ))}
      </g>
      <g opacity={0.55}>
        <Plus cx={24} cy={22} r={6} cls="rdg-s-ink" />
        <Plus cx={1256} cy={22} r={6} cls="rdg-s-ink" />
        <Plus cx={24} cy={94} r={6} cls="rdg-s-ink" />
        <Plus cx={1256} cy={94} r={6} cls="rdg-s-ink" />
      </g>
    </svg>
  )
}
