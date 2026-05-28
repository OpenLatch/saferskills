/**
 * Dark-slate divider with the orange tick-ruler accent — 64px tall.
 * Used as a transition INTO dark sections (install band, CTA band, footer).
 */
export default function RidgePixel({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-pixel ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
    </div>
  )
}
