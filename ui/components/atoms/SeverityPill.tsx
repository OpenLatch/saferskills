/**
 * SeverityPill — the 5-tier severity chip shared by the scan-report finding card
 * (`FindingDetail`) and the public `/methodology` rule cards. Renders the exact
 * ported `.sev` / `.sw` markup (CSS in `ui/styles/components.css`), so the pill is
 * byte-identical wherever a severity is shown.
 *
 * The `Severity` union is defined HERE, inside `ui/` — the design system never
 * imports a generated type from `webapp/` (the one-way boundary). Webapp callers
 * pass a structurally-compatible severity string.
 */

export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export default function SeverityPill({
  severity,
  label,
  className = '',
}: {
  severity: Severity
  /** Override the displayed text (defaults to the upper-cased severity). */
  label?: string
  className?: string
}) {
  return (
    <span className={`sev ${severity} ${className}`.trim()}>
      <span className="sw" aria-hidden="true" />
      {label ?? severity.toUpperCase()}
    </span>
  )
}
