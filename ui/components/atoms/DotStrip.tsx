type Tier = 'green' | 'yellow' | 'orange' | 'red'

const TIER_CLASS: Record<Tier, string> = {
  green: 'dot-g', yellow: 'dot-y', orange: 'dot-o', red: 'dot-r',
}

/**
 * 10-dot strip visualization of a 0-100 score.
 * Filled tier-colored dots = round(value/10); remainder are `dot-off`.
 */
export default function DotStrip({
  value,
  tier,
  className = '',
}: {
  value: number
  tier: Tier
  className?: string
}) {
  const filled = Math.max(0, Math.min(10, Math.round(value / 10)))
  const empty = 10 - filled
  return (
    <span className={`dotstrip ${className}`.trim()} role="img" aria-label={`Score ${value} of 100`}>
      <span className={TIER_CLASS[tier]} aria-hidden="true">
        {'●'.repeat(filled)}
      </span>
      <span className="dot-off" aria-hidden="true">
        {'○'.repeat(empty)}
      </span>
    </span>
  )
}
