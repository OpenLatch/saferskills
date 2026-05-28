import type { Story } from '@ladle/react'

const Mirror = ({
  rank, name, score, tier, installs, delta, featured = false,
}: {
  rank: number
  name: string
  score: number
  tier: 'g' | 'y' | 'o' | 'r'
  installs: string
  delta: string
  featured?: boolean
}) => {
  const filled = Math.max(0, Math.min(10, Math.round(score / 10)))
  const tierLabel = { g: 'GREEN', y: 'YELLOW', o: 'ORANGE', r: 'RED' }[tier]
  return (
    <div className={`trend-card ${featured ? 'featured' : ''}`.trim()}>
      <div className="rank-col">
        <span className="hash">RANK</span>
        <span className="n">#{rank}</span>
      </div>
      <div className="name">{name}</div>
      <span className="score-num">{score}<span className="slash">/100</span></span>
      <div className="dotline">
        <span className="dotstrip">
          <span className={`dot-${tier}`}>{'●'.repeat(filled)}</span>
          <span className="dot-off">{'○'.repeat(10 - filled)}</span>
        </span>
        <span className={`band-pill ${tier}`}>
          <span className={`swatch sw-${tier}`} aria-hidden="true" />
          {tierLabel}
        </span>
      </div>
      <div className="installs">
        <span>
          <span className="num">{installs}</span>
          <span className="lbl">installs · 7d</span>
        </span>
        <span className="delta">{delta}</span>
      </div>
      <div className="spark">
        <span className="blocks">▮▮▮▮▮▮</span>
        <span className="lbl">trend</span>
      </div>
    </div>
  )
}

export const Featured: Story = () => (
  <Mirror rank={1} name="github-mcp" score={94} tier="g" installs="12.4k" delta="+47%" featured />
)
export const TopTen: Story = () => (
  <Mirror rank={2} name="linear-mcp" score={87} tier="g" installs="8.9k" delta="+32%" />
)
export const Mid: Story = () => (
  <Mirror rank={7} name="postgres-mcp" score={72} tier="y" installs="2.1k" delta="+18%" />
)
