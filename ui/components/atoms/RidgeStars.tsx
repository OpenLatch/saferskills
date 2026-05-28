/**
 * Plus-grid constellation divider — 72px tall, paper-deep bg.
 *
 * Layered SVG ported verbatim from the hi-fi mockup: a dashed horizontal
 * seam, a highlighted constellation of `+` plus markers (alternating teal +
 * orange), and ink corner triplets. Sits between the feeds band and the
 * WHY / docs band. `aria-hidden` because it's purely decorative.
 */
export default function RidgeStars({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-stars ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
      <svg
        viewBox="0 0 1280 72"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <line x1="0" y1="36" x2="1280" y2="36" stroke="#0F172A" strokeOpacity="0.32" strokeDasharray="4 7" />
        <g strokeWidth={2} strokeLinecap="square" fill="none">
          <g stroke="#F97316">
            <line x1="100" y1="12" x2="100" y2="24" />
            <line x1="94" y1="18" x2="106" y2="18" />
            <line x1="460" y1="50" x2="460" y2="62" />
            <line x1="454" y1="56" x2="466" y2="56" />
            <line x1="820" y1="14" x2="820" y2="26" />
            <line x1="814" y1="20" x2="826" y2="20" />
            <line x1="1180" y1="48" x2="1180" y2="60" />
            <line x1="1174" y1="54" x2="1186" y2="54" />
          </g>
          <g stroke="#0D9488">
            <line x1="260" y1="50" x2="260" y2="62" />
            <line x1="254" y1="56" x2="266" y2="56" />
            <line x1="620" y1="14" x2="620" y2="26" />
            <line x1="614" y1="20" x2="626" y2="20" />
            <line x1="980" y1="50" x2="980" y2="62" />
            <line x1="974" y1="56" x2="986" y2="56" />
          </g>
        </g>
        <g fill="#0F172A">
          <circle cx="22" cy="36" r="2.5" />
          <circle cx="1258" cy="36" r="2.5" />
        </g>
      </svg>
    </div>
  )
}
