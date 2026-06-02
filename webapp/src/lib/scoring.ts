/** 5-axis rubric taxonomy + locked weights (35/20/15/15/15) — the single source
 * shared by the item-detail score breakdown (`ItemTabs`) and the upload report
 * breakdown (`CapabilityReportTabs`). NOT the mockup's 40/20/15/15/10. Detector
 * blurbs are descriptive config. */
export interface ScoreCategory {
  key: string
  name: string
  weight: number
  detectors: string
}

export const SCORE_CATEGORIES: ScoreCategory[] = [
  { key: 'security', name: 'Security', weight: 35, detectors: 'prompt, exec, net, exfil, eval' },
  {
    key: 'supply_chain',
    name: 'Supply chain',
    weight: 20,
    detectors: 'hash, typosquat, maintainer, lockfile',
  },
  { key: 'maintenance', name: 'Maintenance', weight: 15, detectors: 'staleness, pinning, CI' },
  { key: 'transparency', name: 'Transparency', weight: 15, detectors: 'SKILL.md, perms, README' },
  { key: 'community', name: 'Community', weight: 15, detectors: 'installs, verify, response' },
]
