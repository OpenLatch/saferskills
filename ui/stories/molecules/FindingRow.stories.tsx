import type { Story } from '@ladle/react'
import FindingRow from '../../components/molecules/FindingRow'

export const Critical: Story = () => (
  <ul style={{ listStyle: 'none', padding: 0 }}>
    <FindingRow
      ruleId="SS-HOOKS-RCE-CURL-PIPE-01"
      severity="critical"
      category="Security · Runtime"
      finding="curl | bash pipe found in pre-commit hook"
      matchedContentSha256="a1b2c3d4e5f60718293a4b5c6d7e8f90"
      evidence={{
        filePath: '.claude/hooks/install.sh',
        lineStart: 14,
        lineEnd: 14,
        href: 'https://github.com/acme/foo/blob/abc1234/.claude/hooks/install.sh#L14',
      }}
      remediationLink="https://saferskills.ai/methodology#SS-HOOKS-RCE-CURL-PIPE-01"
    />
  </ul>
)

export const Low: Story = () => (
  <ul style={{ listStyle: 'none', padding: 0 }}>
    <FindingRow
      ruleId="SS-MCP-POISON-DESCRIPTION-CREEP-01"
      severity="low"
      category="Security · Prompt"
      finding="Tool description longer than 240 characters"
      evidence={{ filePath: 'tools/manifest.json', lineStart: 22 }}
      remediationLink="https://saferskills.ai/methodology#SS-MCP-POISON-DESCRIPTION-CREEP-01"
    />
  </ul>
)
