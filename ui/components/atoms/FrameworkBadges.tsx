/**
 * FrameworkBadges — the OWASP LLM Top 10 / MITRE ATLAS / CWE reference-badge row,
 * shared by the scan-report finding card (`FindingDetail`) and the public
 * `/methodology` rule cards. Renders the `.fw-badges` / `.fw-badge` markup (CSS in
 * `ui/styles/components.css`), so both surfaces stay byte-identical and the
 * family-label maps live in exactly one place.
 *
 * The `FrameworkRef` shape + `FrameworkFamily` union are defined HERE in `ui/`
 * (mirroring the generated `FrameworkRef`); the design system never imports a
 * generated type from `webapp/` (the one-way boundary). Callers pass a
 * structurally-compatible array and wrap this row with their own label/container.
 */

export type FrameworkFamily = 'owasp-llm' | 'mitre-atlas' | 'cwe'

export interface FrameworkRef {
  family: FrameworkFamily
  /** Canonical short code, e.g. 'LLM01' / 'AML.T0051' / 'CWE-78'. */
  id: string
  /** Human risk name, e.g. 'Prompt Injection'. */
  label: string
  /** Canonical reference URL. */
  url: string
}

const FAMILY_SHORT: Record<FrameworkFamily, string> = {
  'owasp-llm': 'OWASP',
  'mitre-atlas': 'ATLAS',
  cwe: '', // the CWE id already carries the 'CWE-' prefix
}
const FAMILY_FULL: Record<FrameworkFamily, string> = {
  'owasp-llm': 'OWASP LLM Top 10',
  'mitre-atlas': 'MITRE ATLAS',
  cwe: 'CWE',
}

export default function FrameworkBadges({
  frameworks,
  className = '',
}: {
  frameworks: ReadonlyArray<FrameworkRef>
  className?: string
}) {
  if (frameworks.length === 0) return null
  return (
    <span className={`fw-badges ${className}`.trim()}>
      {frameworks.map((f) => (
        <a
          key={`${f.family}-${f.id}`}
          className={`fw-badge ${f.family}`}
          href={f.url}
          target="_blank"
          rel="noreferrer noopener"
          title={`${FAMILY_FULL[f.family]} — ${f.id} ${f.label}`}
        >
          {FAMILY_SHORT[f.family] ? <span className="fw-fam">{FAMILY_SHORT[f.family]}</span> : null}
          <span className="fw-id">{f.id}</span>
          <span className="fw-ext" aria-hidden="true">
            ↗
          </span>
        </a>
      ))}
    </span>
  )
}
