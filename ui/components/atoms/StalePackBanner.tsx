/**
 * Re-scan nudge shown on a report when a newer pack adds a test for the agent's
 * family. The live badge SVG stays current; this banner lives on
 * the report only. Render conditionally (a data flag); never shown when the pack
 * is current.
 */
export default function StalePackBanner({
  text,
  rescanHref = '/agents',
  className = '',
}: {
  text: string
  rescanHref?: string
  className?: string
}) {
  return (
    <div className={`ar-stale-banner ${className}`.trim()} role="status">
      <svg
        viewBox="0 0 24 24"
        width="15"
        height="15"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden="true"
      >
        <path d="M21 12a9 9 0 1 1-2.64-6.36" />
        <path d="M21 3v6h-6" />
      </svg>
      <span>{text}</span>
      <a href={rescanHref} className="ar-stale-cta">
        Re-scan →
      </a>
    </div>
  )
}
