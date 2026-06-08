/**
 * Sparkline — a compact inline SVG trend line for a small series of numbers
 * (e.g. weekly install counts over a quarter).
 *
 * Token-colored via CSS (`.sparkline*` in ui/styles/components.css) so it flips
 * for dark mode for free. `placeholder` renders the muted/dashed launch-fallback
 * look (used when real data is too thin — the caller decides, per the
 * frontend "live-with-fallback" pattern). Purely presentational; no motion.
 */
interface SparklineProps {
  /** Series oldest→newest. An all-zero / empty series renders a flat baseline. */
  values: number[]
  width?: number
  height?: number
  /** Render the muted, dashed launch-placeholder treatment. */
  placeholder?: boolean
  className?: string
  ariaLabel?: string
}

export default function Sparkline({
  values,
  width = 88,
  height = 26,
  placeholder = false,
  className = '',
  ariaLabel,
}: SparklineProps) {
  const pad = 2
  const max = values.length ? Math.max(0, ...values) : 0
  const span = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0
  const baseline = height - pad
  const points = values.map((v, i) => {
    const x = pad + i * span
    const y = max > 0 ? pad + (height - pad * 2) * (1 - v / max) : baseline
    return [x, y] as const
  })

  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area =
    points.length > 1
      ? `M${points[0][0].toFixed(1)},${baseline.toFixed(1)} ` +
        points.map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(' ') +
        ` L${points[points.length - 1][0].toFixed(1)},${baseline.toFixed(1)} Z`
      : ''

  const total = values.reduce((a, b) => a + b, 0)
  const label =
    ariaLabel ??
    (total > 0
      ? `Install activity: ${total} in the last quarter`
      : 'No recent install activity')

  return (
    <svg
      className={`sparkline${placeholder ? ' sparkline--placeholder' : ''} ${className}`.trim()}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={label}
      preserveAspectRatio="none"
    >
      {area && <path className="sparkline-area" d={area} />}
      {line && <polyline className="sparkline-line" points={line} />}
      {points.length > 0 && (
        <circle
          className="sparkline-dot"
          cx={points[points.length - 1][0].toFixed(1)}
          cy={points[points.length - 1][1].toFixed(1)}
          r={1.6}
        />
      )}
    </svg>
  )
}
