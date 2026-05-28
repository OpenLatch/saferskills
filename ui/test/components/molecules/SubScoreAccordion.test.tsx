import { describe, expect, it } from 'vitest'
import { fireEvent, render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import SubScoreAccordion from '../../../components/molecules/SubScoreAccordion'

const findings = [
  {
    ruleId: 'SS-HOOKS-RCE-CURL-PIPE-01',
    severity: 'critical' as const,
    category: 'Security',
    finding: 'curl | bash',
    evidence: { filePath: 'install.sh', lineStart: 4 },
    remediationLink: 'https://saferskills.ai/methodology#SS-HOOKS-RCE-CURL-PIPE-01',
  },
]

describe('SubScoreAccordion', () => {
  it('renders collapsed by default', () => {
    const { container } = render(
      <SubScoreAccordion
        label="Security"
        subScoreKey="security"
        value={40}
        weight={35}
        tier="orange"
        findings={findings}
      />,
    )
    expect(container.querySelector('.subscore-accordion-body')).toBeNull()
  })

  it('expands on click', () => {
    const { container } = render(
      <SubScoreAccordion
        label="Security"
        subScoreKey="security"
        value={40}
        weight={35}
        tier="orange"
        findings={findings}
      />,
    )
    const button = container.querySelector('.subscore-accordion-head') as HTMLButtonElement
    fireEvent.click(button)
    expect(container.querySelector('.subscore-accordion-body')).not.toBeNull()
  })

  it('is accessible when open (vitest-axe)', async () => {
    const { container } = render(
      <SubScoreAccordion
        label="Security"
        subScoreKey="security"
        value={40}
        weight={35}
        tier="orange"
        findings={findings}
        defaultOpen
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
