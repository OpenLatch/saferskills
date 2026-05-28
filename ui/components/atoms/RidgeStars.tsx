/**
 * Plus-grid horizontal divider — 72px tall, paper-deep bg, optional centered
 * uppercase mono label.
 */
export default function RidgeStars({
  label,
  className = '',
}: { label?: string; className?: string }) {
  return (
    <div className={`ridge ridge-stars ${className}`.trim()} aria-hidden="true">
      {label && <span className="ridge-label">{label}</span>}
    </div>
  )
}
