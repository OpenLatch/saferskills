type Size = 'sm' | 'md' | 'lg' | 'hero'

const SIZE_PX: Record<Size, number> = { sm: 22, md: 28, lg: 36, hero: 80 }

/**
 * "Loud" score display — Anybody 800 wdth=125%, signature giant number.
 * Slash + denominator render in mono at 0.32em of the main size.
 */
export default function ScoreNumber({
  value,
  max = 100,
  size = 'md',
  className = '',
}: {
  value: number
  max?: number
  size?: Size
  className?: string
}) {
  const px = SIZE_PX[size]
  return (
    <span className={`score-num ${className}`.trim()} style={{ fontSize: px }}>
      {value}
      <span className="slash">/{max}</span>
    </span>
  )
}
