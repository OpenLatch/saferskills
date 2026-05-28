type Tier = 'green' | 'yellow' | 'orange' | 'red'

const TIER_TO_VARIANT: Record<Tier, 'g' | 'y' | 'o' | 'r'> = {
  green: 'g', yellow: 'y', orange: 'o', red: 'r',
}

/**
 * `[● GREEN]` style tier label — paper-deep bg with tier-tinted hairline,
 * 10×10 colored swatch, mono uppercase 10px 700 letter-spaced label.
 */
export default function BandPill({
  tier,
  label,
  className = '',
}: {
  tier: Tier
  label?: string
  className?: string
}) {
  const v = TIER_TO_VARIANT[tier]
  return (
    <span className={`band-pill ${v} ${className}`.trim()}>
      <span className={`swatch sw-${v}`} aria-hidden="true" />
      {label ?? tier.toUpperCase()}
    </span>
  )
}
