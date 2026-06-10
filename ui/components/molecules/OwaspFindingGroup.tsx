import type { ReactNode } from 'react'

import RefChip, { type RefChipProps } from '../atoms/RefChip'

export interface OwaspFindingGroupProps {
  /** OWASP index shown in the head, e.g. `ASI04` / `LLM01`. */
  index: string
  /** Family title, e.g. `Tool-description poisoning`. */
  title: string
  /** Deep-linked OWASP / MITRE refs for the family. */
  refs: RefChipProps[]
  /** The finding cards (composed by the report island). */
  children: ReactNode
}

/**
 * OWASP-family finding group (I-5.6 §9). Renders the group head — OWASP index +
 * family title + a row of deep-linked `RefChip`s — wrapping the finding cards the
 * report island composes. The `.find-card` chrome the cards reuse is DS-owned;
 * this molecule owns only the `.owasp-group*` head CSS (components.css).
 */
export default function OwaspFindingGroup({
  index,
  title,
  refs,
  children,
}: OwaspFindingGroupProps) {
  return (
    <section className="owasp-group">
      <header className="owasp-group-head">
        {index ? <span className="og-ix">{index}</span> : null}
        <span className="og-title">{title}</span>
        {refs.length > 0 ? (
          <span className="og-refs">
            {refs.map((r) => (
              <RefChip key={`${r.kind}-${r.label}`} {...r} />
            ))}
          </span>
        ) : null}
      </header>
      {children}
    </section>
  )
}
