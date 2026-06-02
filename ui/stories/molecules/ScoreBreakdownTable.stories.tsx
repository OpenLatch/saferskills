import type { Story } from '@ladle/react'
import ScoreBreakdownTable, {
  type ScoreCategoryRow,
} from '../../components/molecules/ScoreBreakdownTable'

// Mirrors webapp's SCORE_CATEGORIES (35/20/15/15/15) — passed in by the caller
// so ui/ stays decoupled from webapp config.
const CATEGORIES: ScoreCategoryRow[] = [
  { key: 'security', name: 'Security', weight: 35, detectors: 'prompt, exec, net, exfil, eval' },
  { key: 'supply_chain', name: 'Supply chain', weight: 20, detectors: 'hash, typosquat, maintainer, lockfile' },
  { key: 'maintenance', name: 'Maintenance', weight: 15, detectors: 'staleness, pinning, CI' },
  { key: 'transparency', name: 'Transparency', weight: 15, detectors: 'SKILL.md, perms, README' },
  { key: 'community', name: 'Community', weight: 15, detectors: 'installs, verify, response' },
]

export const Default: Story = () => (
  <div style={{ maxWidth: 720, padding: 40 }}>
    <ScoreBreakdownTable
      categories={CATEGORIES}
      subScores={{ security: 82, supply_chain: 64, maintenance: 91, transparency: 70, community: 55 }}
    />
  </div>
)

export const PerfectAndZero: Story = () => (
  <div style={{ maxWidth: 720, padding: 40 }}>
    <ScoreBreakdownTable
      categories={CATEGORIES}
      subScores={{ security: 100, supply_chain: 0, maintenance: 100, transparency: 0, community: 100 }}
    />
  </div>
)

export const MissingSubScores: Story = () => (
  <div style={{ maxWidth: 720, padding: 40 }}>
    {/* Absent keys fall back to 0. */}
    <ScoreBreakdownTable categories={CATEGORIES} subScores={{ security: 48 }} />
  </div>
)
