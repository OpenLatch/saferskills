import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CorpusRiskMeter from '../../../components/molecules/CorpusRiskMeter'

describe('CorpusRiskMeter', () => {
  it('shows the published rate + claim when the gate is met', () => {
    render(<CorpusRiskMeter pctWithCritical={41} gateMet corpusCount={812} gateTarget={500} />)
    expect(screen.getByText('41%')).toBeInTheDocument()
    expect(
      screen.getByText('of assessed agents carry at least one critical finding')
    ).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('shows the collecting gate (blank %, progress bar) below the gate', () => {
    render(
      <CorpusRiskMeter pctWithCritical={null} gateMet={false} corpusCount={134} gateTarget={500} />
    )
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText(/gated until n ≥ 500 · 134\/500 so far/)).toBeInTheDocument()
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '134')
    expect(bar).toHaveAttribute('aria-valuemax', '500')
  })

  it('has no critical a11y violations (both states)', async () => {
    const a = render(<CorpusRiskMeter pctWithCritical={41} gateMet corpusCount={812} gateTarget={500} />)
    expect((await axe(a.container)).violations).toHaveLength(0)
    const b = render(
      <CorpusRiskMeter pctWithCritical={null} gateMet={false} corpusCount={1} gateTarget={500} />
    )
    expect((await axe(b.container)).violations).toHaveLength(0)
  })
})
