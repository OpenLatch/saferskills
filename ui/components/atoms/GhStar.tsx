const GH_ICON = (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path
      fillRule="evenodd"
      d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z"
    />
  </svg>
)

const formatStars = (n: number): string => {
  if (n >= 1000) {
    return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`
  }
  return String(n)
}

/**
 * GitHub star CTA — paired chamfered segments. Left: dark ink with GitHub
 * star icon + "Star" label. Right: teal-tint with mono count. Hover lifts -1px
 * + right segment becomes citron.
 */
export default function GhStar({
  repo = 'OpenLatch/saferskills',
  count,
  className = '',
}: {
  repo?: string
  count: number
  className?: string
}) {
  return (
    <a
      className={`gh-star ${className}`.trim()}
      href={`https://github.com/${repo}`}
      target="_blank"
      rel="noopener"
      aria-label={`Star ${repo} on GitHub`}
    >
      <span className="gh-l">{GH_ICON} Star</span>
      <span className="gh-r">{formatStars(count)}</span>
    </a>
  )
}
