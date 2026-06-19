/**
 * Public-route evidence note — stands in for the redacted transcript on the public
 * report (the transcript hydrates only on the unlisted token route).
 * Default copy: "transcript withheld on the public report".
 */
export default function EvidenceWithheldNote({
  text = 'transcript withheld on the public report',
  className = '',
}: {
  text?: string
  className?: string
}) {
  return (
    <p className={`evidence-public-note ${className}`.trim()}>
      <svg
        viewBox="0 0 24 24"
        width="13"
        height="13"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        aria-hidden="true"
      >
        <rect x="4" y="11" width="16" height="10" />
        <path d="M7.5 11V7.5a4.5 4.5 0 0 1 9 0V11" />
      </svg>
      {text}
    </p>
  )
}
