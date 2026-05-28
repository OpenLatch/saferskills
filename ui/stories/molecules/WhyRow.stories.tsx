import type { Story } from '@ladle/react'
import WhyRow from '../../components/molecules/WhyRow'

export const Verify: Story = () => (
  <WhyRow
    index="01"
    tag="verify"
    body={
      <>
        Every skill is scored against <b>five sub-rubrics</b> — security, supply chain,
        maintenance, transparency, community — with deterministic, quotable rule_ids.
      </>
    }
    metaLines={[
      'methodology · open source',
      <a href="/methodology" className="link">read the rubric →</a>,
    ]}
  />
)

export const Monitor: Story = () => (
  <WhyRow
    index="02"
    tag="monitor"
    body="On-push rescans + monthly deepscans. Drift gets a finding, not silence."
  />
)

export const Trust: Story = () => (
  <WhyRow
    index="03"
    tag="trust"
    body={<>Every <b>verdict is appealable</b>. Vendor right-of-reply is structural.</>}
    metaLines={['verified appeal · 1h SLA']}
  />
)
