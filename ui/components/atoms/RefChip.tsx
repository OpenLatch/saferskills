export type RefKind = 'owasp' | 'mitre' | 'nist'

export interface RefChipProps {
  /** Reference id shown in the chip, e.g. `ASI04:2026` / `AML.T0053` / `NIST AI 600-1`. */
  label: string
  /** Deep-link target (external). */
  href: string
  /** Framework family — tints the `.k` label + the chip role. */
  kind: RefKind
}

/**
 * Deep-linked OWASP / MITRE ATLAS / NIST reference chip. Renders an
 * external `<a>` (`rel="noopener noreferrer"`) with a tinted id label + an
 * external-link affordance. Used in the OWASP-family group head (`.og-refs`) and
 * per-finding refs row (`.fc-refs`). CSS `.ref-chip` is DS-owned in components.css.
 */
export default function RefChip({ label, href, kind }: RefChipProps) {
  return (
    <a className={`ref-chip ${kind}`} href={href} target="_blank" rel="noopener noreferrer">
      <span className="k">{label}</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
        <path d="M7 17 17 7M9 7h8v8" />
      </svg>
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  )
}
