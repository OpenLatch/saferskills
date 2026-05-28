import type { Story } from '@ladle/react'

// RecentScanCard is an Astro component. Ladle renders a React mirror that
// matches the static HTML output for visual review.

const Mirror = ({
  name, author, kind, score, tier, scannedAtRelative, findingCount,
}: {
  name: string
  author: string
  kind: 'skill' | 'mcp_server' | 'hook' | 'plugin' | 'rules'
  score: number
  tier: 'g' | 'y' | 'o' | 'r'
  scannedAtRelative: string
  findingCount?: number
}) => {
  const filled = Math.max(0, Math.min(10, Math.round(score / 10)))
  return (
    <div className="recent-card">
      <div>
        <div className="meta">SCAN · {scannedAtRelative}</div>
        <div className="name">{name}</div>
        <div className="meta">
          {author} · {kind.replace('_', ' ')}
          {typeof findingCount === 'number' && findingCount > 0 && (
            <span className="warn"> · {findingCount} finding{findingCount === 1 ? '' : 's'}</span>
          )}
        </div>
      </div>
      <div className="score-block">
        <span className="score-num">{score}<span className="slash">/100</span></span>
      </div>
      <div className="dotline">
        <span className="dotstrip">
          <span className={`dot-${tier}`}>{'●'.repeat(filled)}</span>
          <span className="dot-off">{'○'.repeat(10 - filled)}</span>
        </span>
        <span className={`band-pill ${tier}`}>
          <span className={`swatch sw-${tier}`} aria-hidden="true" />
          {(['g','y','o','r'].includes(tier) ? { g: 'GREEN', y: 'YELLOW', o: 'ORANGE', r: 'RED' }[tier] : '')}
        </span>
      </div>
    </div>
  )
}

export const Green: Story = () => (
  <Mirror name="github-mcp" author="modelcontextprotocol" kind="mcp_server" score={87} tier="g" scannedAtRelative="2m ago" />
)

export const Yellow: Story = () => (
  <Mirror name="linear-mcp" author="acme" kind="mcp_server" score={72} tier="y" scannedAtRelative="18m ago" findingCount={3} />
)

export const Red: Story = () => (
  <Mirror name="dodgy-skill" author="alice" kind="skill" score={29} tier="r" scannedAtRelative="1h ago" findingCount={11} />
)
