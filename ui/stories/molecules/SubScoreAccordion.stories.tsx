import type { Story } from '@ladle/react'
import SubScoreAccordion from '../../components/molecules/SubScoreAccordion'

const findings = [
  {
    ruleId: 'SS-HOOKS-RCE-CURL-PIPE-01',
    severity: 'critical' as const,
    category: 'Security · Runtime',
    finding: 'curl | bash pipe found in install hook',
    evidence: { filePath: '.claude/hooks/install.sh', lineStart: 14 },
    remediationLink: 'https://saferskills.ai/methodology#SS-HOOKS-RCE-CURL-PIPE-01',
  },
  {
    ruleId: 'SS-SKILL-INJECT-IGNORE-01',
    severity: 'high' as const,
    category: 'Security · Prompt',
    finding: 'Imperative pattern: "ignore previous instructions"',
    evidence: { filePath: 'SKILL.md', lineStart: 42 },
    remediationLink: 'https://saferskills.ai/methodology#SS-SKILL-INJECT-IGNORE-01',
  },
]

export const SecurityOpen: Story = () => (
  <SubScoreAccordion
    label="Security"
    subScoreKey="security"
    value={40}
    weight={35}
    tier="orange"
    criticalFloorApplied
    findings={findings}
    defaultOpen
  />
)

export const SupplyChainClear: Story = () => (
  <SubScoreAccordion
    label="Supply chain"
    subScoreKey="supply_chain"
    value={95}
    weight={20}
    tier="green"
    findings={[]}
    defaultOpen
  />
)
