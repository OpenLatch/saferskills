/**
 * Gradient-transition divider — 88px tall, paper-deep → paper.
 */
export default function RidgeFlow({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-flow ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
    </div>
  )
}
