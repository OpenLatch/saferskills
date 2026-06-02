import type { Story } from '@ladle/react'
import CheckGroupList, {
  type CheckGroupCategory,
  type CheckGroupFinding,
} from '../../components/molecules/CheckGroupList'

const CATEGORIES: CheckGroupCategory[] = [
  { key: 'security', name: 'Security' },
  { key: 'supply_chain', name: 'Supply chain' },
  { key: 'maintenance', name: 'Maintenance' },
  { key: 'transparency', name: 'Transparency' },
  { key: 'community', name: 'Community' },
]

const SUB = { security: 42, supply_chain: 88, maintenance: 70, transparency: 95, community: 60 }

const FINDINGS: CheckGroupFinding[] = [
  {
    id: 'f1',
    ruleId: 'SS-HOOKS-RCE-CURL-PIPE-01',
    severity: 'critical',
    subScore: 'security',
    filePath: '.claude/hooks/install.sh',
    lineStart: 14,
  },
  {
    id: 'f2',
    ruleId: 'SS-MCP-POISON-DESCRIPTION-CREEP-01',
    severity: 'medium',
    subScore: 'security',
    filePath: 'tools/manifest.json',
    lineStart: 22,
  },
  {
    id: 'f3',
    ruleId: 'SS-SKILL-STALE-PIN-01',
    severity: 'low',
    subScore: 'maintenance',
    filePath: 'package.json',
    lineStart: 3,
  },
]

export const Mixed: Story = () => (
  <div style={{ maxWidth: 720, padding: 40 }}>
    <CheckGroupList categories={CATEGORIES} subScores={SUB} findings={FINDINGS} />
  </div>
)

export const AllPassing: Story = () => (
  <div style={{ maxWidth: 720, padding: 40 }}>
    <CheckGroupList
      categories={CATEGORIES}
      subScores={{ security: 100, supply_chain: 100, maintenance: 100, transparency: 100, community: 100 }}
      findings={[]}
      emptyScanNoun="the latest scan"
    />
  </div>
)
