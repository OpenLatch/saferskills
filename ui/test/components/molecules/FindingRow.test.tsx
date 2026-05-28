import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import FindingRow from '../../../components/molecules/FindingRow'

describe('FindingRow', () => {
  it('renders rule + severity + evidence', () => {
    const { container } = render(
      <ul>
        <FindingRow
          ruleId="SS-HOOKS-RCE-CURL-PIPE-01"
          severity="critical"
          category="Security"
          finding="curl | bash"
          evidence={{ filePath: 'install.sh', lineStart: 4 }}
          remediationLink="https://saferskills.ai/methodology#SS-HOOKS-RCE-CURL-PIPE-01"
        />
      </ul>,
    )
    expect(container.querySelector('.finding-row')).not.toBeNull()
    expect(container.querySelector('.finding-row-rule code')?.textContent).toBe('SS-HOOKS-RCE-CURL-PIPE-01')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <ul>
        <FindingRow
          ruleId="SS-X-Y-01"
          severity="low"
          category="Test"
          finding="x"
          evidence={{ filePath: 'a.md', lineStart: 1 }}
          remediationLink="https://saferskills.ai/methodology#SS-X-Y-01"
        />
      </ul>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
