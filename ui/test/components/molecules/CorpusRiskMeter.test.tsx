import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import CorpusRiskMeter from '../../../components/molecules/CorpusRiskMeter'

describe('CorpusRiskMeter', () => {
  it('shows the published rate + claim when the gate is met', () => {
    render(
      <CorpusRiskMeter
        pctWithCritical={41}
        gateMet
        corpusCount={812}
        gateTarget={500}
        packTestCount={17}
      />
    )
    expect(screen.getByText('41%')).toBeInTheDocument()
    expect(
      screen.getByText('of assessed agents carry at least one critical finding')
    ).toBeInTheDocument()
    // No methodology instrument (no headline) in the published state.
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument()
  })

  it('shows the methodology instrument (pack size · frameworks · count · gate footnote) below the gate', () => {
    render(
      <CorpusRiskMeter
        pctWithCritical={null}
        gateMet={false}
        corpusCount={134}
        gateTarget={500}
        packTestCount={17}
      />
    )
    // Leads with the pack, not an apology — no published "—" rate.
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(
      'Every agent meets the full adversarial pack.'
    )
    expect(screen.queryByText('—')).not.toBeInTheDocument()
    // Cell 1: live pack size. Cell 3: live corpus count.
    expect(screen.getByText('17')).toBeInTheDocument()
    expect(screen.getByText('134')).toBeInTheDocument()
    // Cell 2: framework coverage chips.
    expect(screen.getByText('OWASP Agentic')).toBeInTheDocument()
    expect(screen.getByText('MITRE ATLAS')).toBeInTheDocument()
    // The gate is a quiet footnote naming the target, not the headline.
    expect(screen.getByText(/publishes at/)).toHaveTextContent('500 scans')
  })

  it('has no critical a11y violations (both states)', async () => {
    const a = render(
      <CorpusRiskMeter
        pctWithCritical={41}
        gateMet
        corpusCount={812}
        gateTarget={500}
        packTestCount={17}
      />
    )
    expect((await axe(a.container)).violations).toHaveLength(0)
    const b = render(
      <CorpusRiskMeter
        pctWithCritical={null}
        gateMet={false}
        corpusCount={1}
        gateTarget={500}
        packTestCount={17}
      />
    )
    expect((await axe(b.container)).violations).toHaveLength(0)
  })
})
