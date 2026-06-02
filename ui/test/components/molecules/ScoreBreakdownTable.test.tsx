import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ScoreBreakdownTable, {
  type ScoreCategoryRow,
} from '../../../components/molecules/ScoreBreakdownTable'

const CATEGORIES: ScoreCategoryRow[] = [
  { key: 'security', name: 'Security', weight: 35, detectors: 'prompt, exec' },
  { key: 'community', name: 'Community', weight: 15, detectors: 'installs, verify' },
]

describe('ScoreBreakdownTable', () => {
  it('renders one row per category plus the header row', () => {
    const { container } = render(
      <ScoreBreakdownTable categories={CATEGORIES} subScores={{ security: 80, community: 60 }} />,
    )
    // header row + 2 data rows
    expect(container.querySelectorAll('.sc-row').length).toBe(3)
    expect(container.querySelector('.sc-row.sc-head')).not.toBeNull()
  })

  it('computes weighted contribution = score × weight / 100', () => {
    const { container } = render(
      <ScoreBreakdownTable categories={CATEGORIES} subScores={{ security: 80, community: 60 }} />,
    )
    const contribs = [...container.querySelectorAll('.sc-contrib b')].map((n) => n.textContent)
    // 80 × 35 / 100 = 28.0 ; 60 × 15 / 100 = 9.0
    expect(contribs).toEqual(['28.0', '9.0'])
  })

  it('falls back to 0 for a missing sub-score', () => {
    const { container } = render(
      <ScoreBreakdownTable categories={CATEGORIES} subScores={{ security: 80 }} />,
    )
    const nums = [...container.querySelectorAll('.sc-bar .num')].map((n) => n.textContent)
    expect(nums).toEqual(['80', '0'])
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <ScoreBreakdownTable categories={CATEGORIES} subScores={{ security: 80, community: 60 }} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
