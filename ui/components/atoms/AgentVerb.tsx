export type AgentVerbBand = 'green' | 'yellow' | 'orange' | 'red' | 'unscoped'

const VERB: Record<AgentVerbBand, string> = {
  green: 'Ship',
  yellow: 'Review',
  orange: 'Remediate',
  red: 'Do-Not-Deploy',
  unscoped: 'Unscoped',
}

/**
 * The band verb in the behavioral-score hero (`Ship` / `Review` / `Remediate` /
 * `Do-Not-Deploy`). Loud Anybody display type; color is inherited from the
 * enclosing `.score-cell.{g|y|o|r}`. A leading `·` separator
 * sets it off from the band pill.
 */
export default function AgentVerb({
  band,
  className = '',
}: {
  band: AgentVerbBand
  className?: string
}) {
  return (
    <span className={`ar-verb ${className}`.trim()}>
      <span className="vb-sep" aria-hidden="true">
        ·
      </span>
      {VERB[band]}
    </span>
  )
}
