export type ProvenanceTone = 'default' | 'tier' | 'pack'

export interface ProvenanceChip {
  label: string
  /** Hover/`title` tooltip describing the provenance fact. */
  title?: string
  tone?: ProvenanceTone
}

/**
 * Badge-band provenance chips — `OWASP Agentic` · `MITRE ATLAS` ·
 * `cloud-validated`/`client-administered` · `Apache-2.0`, each with a tooltip.
 * Pure presentational; CSS `.prov-chip` / `.ar-prov-chips` is DS-owned in
 * components.css.
 */
export default function ProvenanceChips({ chips }: { chips: ProvenanceChip[] }) {
  return (
    <div className="ar-prov-chips">
      {chips.map((c) => (
        <span
          key={c.label}
          className={`prov-chip${c.tone && c.tone !== 'default' ? ` ${c.tone}` : ''}`}
          title={c.title}
        >
          {c.label}
        </span>
      ))}
    </div>
  )
}
