import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RiskThermometer from '../../../components/molecules/RiskThermometer'

const DIST = {
  red: { pct: 41, count: 333 },
  orange: { pct: 19, count: 154 },
  yellow: { pct: 22, count: 179 },
  green: { pct: 18, count: 146 },
}

describe('RiskThermometer', () => {
  it('renders the window label, count, and band legend', () => {
    render(
      <RiskThermometer distribution={DIST} windowLabel="Whole corpus · Last 3 months" corpusCount={812} />
    )
    expect(screen.getByText('Risk distribution · Whole corpus · Last 3 months')).toBeInTheDocument()
    expect(screen.getByText('812')).toBeInTheDocument()
    expect(screen.getByText(/Red · 0–39/)).toBeInTheDocument()
    expect(screen.getByText(/Green · 80–100/)).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <RiskThermometer distribution={DIST} windowLabel="Whole corpus · Last 3 months" corpusCount={812} />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
