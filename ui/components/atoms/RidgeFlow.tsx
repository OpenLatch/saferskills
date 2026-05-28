/**
 * Sine-wave bundle divider — 104px tall, paper-deep → paper gradient.
 *
 * Layered SVG ported verbatim from the hi-fi mockup: 7 alternating teal /
 * orange / ink contour curves plus a scattered `+` marker constellation.
 * Used as the transition between the WHY/docs band and the detection band.
 * `aria-hidden` because it's purely decorative.
 */
export default function RidgeFlow({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-flow ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
      <svg
        viewBox="0 0 1280 104"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g fill="none" strokeWidth={1.2} strokeLinecap="round">
          <path d="M0,22 C140,8 280,38 420,22 C560,8 700,38 840,22 C980,8 1120,32 1280,22" stroke="#0D9488" strokeOpacity="0.35" />
          <path d="M0,32 C140,18 280,48 420,32 C560,18 700,48 840,32 C980,18 1120,42 1280,32" stroke="#F97316" strokeOpacity="0.50" />
          <path d="M0,42 C140,28 280,58 420,42 C560,28 700,58 840,42 C980,28 1120,52 1280,42" stroke="#0F172A" strokeOpacity="0.28" />
          <path d="M0,52 C140,38 280,68 420,52 C560,38 700,68 840,52 C980,38 1120,62 1280,52" stroke="#0D9488" strokeOpacity="0.65" strokeWidth={1.4} />
          <path d="M0,62 C140,48 280,78 420,62 C560,48 700,78 840,62 C980,48 1120,72 1280,62" stroke="#0F172A" strokeOpacity="0.32" />
          <path d="M0,72 C140,58 280,88 420,72 C560,58 700,88 840,72 C980,58 1120,82 1280,72" stroke="#F97316" strokeOpacity="0.70" strokeWidth={1.4} />
          <path d="M0,84 C140,70 280,98 420,84 C560,70 700,98 840,84 C980,70 1120,92 1280,84" stroke="#0F172A" strokeOpacity="0.18" />
        </g>
        <g strokeWidth={0.9} strokeLinecap="square" opacity={0.55}>
          <g stroke="#0F172A">
            <line x1="180" y1="8" x2="180" y2="16" />
            <line x1="176" y1="12" x2="184" y2="12" />
            <line x1="720" y1="6" x2="720" y2="14" />
            <line x1="716" y1="10" x2="724" y2="10" />
          </g>
          <g stroke="#F97316" opacity={0.85}>
            <line x1="460" y1="10" x2="460" y2="18" />
            <line x1="456" y1="14" x2="464" y2="14" />
            <line x1="1020" y1="8" x2="1020" y2="16" />
            <line x1="1016" y1="12" x2="1024" y2="12" />
          </g>
        </g>
      </svg>
    </div>
  )
}
