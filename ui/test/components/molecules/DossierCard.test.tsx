import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import DossierCard from '../../../components/molecules/DossierCard'

const EMPTY_TALLY = { skill: 0, hook: 0, mcp: 0, plugin: 0, rules: 0 }

const base = {
  agentName: 'acme-agent',
  runtime: 'claude-code',
  scannedAt: '2026-06-09T12:00:00Z',
  now: Date.parse('2026-06-09T16:00:00Z'),
  capabilityTally: EMPTY_TALLY,
  href: '/agents/demo',
}

describe('DossierCard', () => {
  it('links to the report and shows severity pills for a critical-bearing run', () => {
    const { container } = render(
      <DossierCard
        {...base}
        score={34}
        band="red"
        findings={{ critical: 1, high: 2, info: 0, total: 3 }}
      />
    )
    expect(screen.getByRole('link', { name: /acme-agent/ })).toHaveAttribute('href', '/agents/demo')
    expect(screen.getByText('1 critical')).toBeInTheDocument()
    expect(screen.getByText('2 high')).toBeInTheDocument()
    expect(container.querySelector('.dossier')?.classList.contains('crit-row')).toBe(true)
  })

  it('shows "No findings" for a clean run', () => {
    const { container } = render(
      <DossierCard
        {...base}
        score={92}
        band="green"
        findings={{ critical: 0, high: 0, info: 0, total: 0 }}
      />
    )
    expect(screen.getByText('No findings')).toBeInTheDocument()
    expect(screen.getByText('4h ago')).toBeInTheDocument()
    expect(container.querySelector('.dossier')?.classList.contains('crit-row')).toBe(false)
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <DossierCard {...base} score={34} band="red" findings={{ critical: 1, high: 0, info: 0, total: 1 }} />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
