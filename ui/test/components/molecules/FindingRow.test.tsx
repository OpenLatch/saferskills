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
    expect(container.querySelector('.fr-rule code')?.textContent).toBe('SS-HOOKS-RCE-CURL-PIPE-01')
    // The rule_id links to the methodology (the "risk" reference).
    expect(container.querySelector('.fr-rule')?.getAttribute('href')).toContain('/methodology#')
  })

  it('renders a SHA copy button + a GitHub button, replacing the raw path link', () => {
    const { container, getByRole } = render(
      <ul>
        <FindingRow
          ruleId="SS-SKILL-INJECT-FENCED-RUN-01"
          severity="high"
          category="Security"
          matchedContentSha256="af3a33314e6800112233445566778899aabbccddeeff00112233445566778899"
          evidence={{
            filePath: 'skills/.curated/cloudflare-deploy/references/miniflare/gotchas.md',
            lineStart: 24,
            lineEnd: 45,
            href: 'https://github.com/openai/skills/blob/abc/.../gotchas.md#L24',
          }}
          remediationLink="https://saferskills.ai/methodology#SS-SKILL-INJECT-FENCED-RUN-01"
        />
      </ul>,
    )
    // SHA chip is truncated + has a copy button.
    expect(container.querySelector('.fr-sha code')?.textContent).toBe('sha256:af3a33314e68…')
    expect(getByRole('button', { name: /copy sha-256/i })).not.toBeNull()
    // The GitHub navigation is a button (anchor), not raw path text.
    const gh = getByRole('link', { name: /view on github/i })
    expect(gh.getAttribute('href')).toContain('github.com')
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
