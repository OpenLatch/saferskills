import type { Story } from '@ladle/react'
import WhyRow from '../../components/molecules/WhyRow'

/**
 * WhyRow — Phase A2 `.reason-row` vocabulary. Inline 4-column row used inside
 * the `.docs-band` "Five reasons it earns the URL" man-page layout.
 */

export const Find: Story = () => (
  <div className="reasons-list" style={{ borderTop: '1px solid var(--color-ink)' }}>
    <WhyRow
      index="01"
      tag="find"
      body={
        <>
          <b>Unified catalog across 12+ registries.</b>
          <span>GitHub, npm, PyPI, MCP Registry, mcp.so, Smithery, Glama, PulseMCP, ClawHub, skillsmp, skills.sh, ClaudeSkills, SkillHub. One search instead of twelve.</span>
        </>
      }
      metaLines={[
        <><b>12,847</b>indexed</>,
        <>updated hourly</>,
      ]}
      arrow={{ label: 'open methodology', href: '/methodology' }}
    />
  </div>
)

export const FullList: Story = () => (
  <div className="reasons-list" style={{ borderTop: '1px solid var(--color-ink)' }}>
    <WhyRow
      index="01"
      tag="find"
      body={<><b>Unified catalog across 12+ registries.</b><span>One search instead of twelve.</span></>}
      metaLines={[<><b>12,847</b>indexed</>]}
      arrow={{ label: 'open methodology', href: '/methodology' }}
    />
    <WhyRow
      index="02"
      tag="verify"
      body={<><b>Independent, transparent scoring.</b><span>87 deterministic detection rules. Every finding cites a rule ID.</span></>}
      metaLines={[<><b>87</b>rules</>]}
      arrow={{ label: 'rule index', href: '/methodology' }}
    />
    <WhyRow
      index="03"
      tag="monitor"
      body={<><b>Watch any skill.</b><span>Drift alerts when content changes. Risk alerts on score drops.</span></>}
      metaLines={[<>email-gated</>, <><b>≤ 5</b>alerts / day</>]}
      arrow={{ label: 'account self-deletion', href: '/docs#account' }}
    />
  </div>
)
