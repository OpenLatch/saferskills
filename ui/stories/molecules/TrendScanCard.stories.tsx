import type { Story } from '@ladle/react'

/**
 * TrendScanCard — `.scan-card.trend` vocabulary.
 *
 * React mirror of the Astro shell for Ladle visual review. CSS contract
 * lives in `webapp/src/styles/page-home.css::.feeds-band .scan-card.trend`.
 */
const TIER_TO_BAND = { g: 'Green', y: 'Yellow', o: 'Orange', r: 'Red' } as const

const Mirror = ({
  rank,
  name,
  score,
  tier,
  installs,
  delta,
  spark = '▁▂▂▃▅▇█',
}: {
  rank: number
  name: string
  score: number
  tier: keyof typeof TIER_TO_BAND
  installs: string
  delta: string
  spark?: string
}) => {
  const iconMono = tier === 'g' ? 'G' : tier === 'y' ? 'Y' : 'O'
  const iconMod = tier === 'g' ? '' : tier === 'y' ? 'yellow' : 'orange'
  const swClass = tier === 'g' ? 'green' : tier === 'y' ? 'yellow' : 'orange'
  return (
    <div className="feeds-band" style={{ maxWidth: 400 }}>
      <div className="mosaic" style={{ display: 'block' }}>
        <a className="scan-card trend" href="#" aria-label={`#${rank} ${name}`}>
          <div className="row">
            <div className="body">
              <div className="rank-pill">TRENDING · <b>#{rank}</b></div>
              <div className="name">{name}</div>
              <div className="meta">{score}/100 · {TIER_TO_BAND[tier]} band</div>
            </div>
            <span className={`icon-mark ${iconMod}`.trim()}>{iconMono}</span>
          </div>
          <div className="trend-stats">
            <div><span className="num">{installs}</span> installs / wk</div>
            <div className="delta">{delta} ↑</div>
          </div>
          <div className="score-line">
            <div className="trend-spark">{spark}</div>
            <span className="band" style={{ marginLeft: 'auto' }}>
              <span className={`sw ${swClass}`}></span>7-day
            </span>
          </div>
        </a>
      </div>
    </div>
  )
}

export const Top1: Story = () => (
  <Mirror rank={1} name="linear-mcp" score={96} tier="g" installs="1,247" delta="+312%" spark="▁▂▂▃▅▇█" />
)
export const Top2: Story = () => (
  <Mirror rank={2} name="notion-mcp" score={88} tier="g" installs="873" delta="+94%" spark="▁▂▃▃▄▆▇" />
)
export const Top3: Story = () => (
  <Mirror rank={3} name="neon-mcp" score={84} tier="g" installs="612" delta="+58%" spark="▁▁▂▃▄▅▆" />
)
