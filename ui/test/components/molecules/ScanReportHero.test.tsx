import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ScanReportHero from '../../../components/molecules/ScanReportHero'

const sub = [
  { label: 'Security', key: 'security', value: 78, weight: 35 },
  { label: 'Supply chain', key: 'supply_chain', value: 92, weight: 20 },
]

describe('ScanReportHero', () => {
  it('renders the report-hero scaffold', () => {
    const { container } = render(<ScanReportHero score={87} tier="green" subScores={sub} />)
    expect(container.querySelector('.report-hero')).not.toBeNull()
    expect(container.querySelector('.report-hero-score')).not.toBeNull()
  })

  it('renders sub-score rows', () => {
    const { container } = render(<ScanReportHero score={87} tier="green" subScores={sub} />)
    expect(container.querySelectorAll('.report-hero-subscore-row').length).toBe(2)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ScanReportHero score={50} tier="orange" subScores={sub} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
