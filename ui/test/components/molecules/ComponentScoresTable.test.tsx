import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ComponentScoresTable from '../../../components/molecules/ComponentScoresTable'

const ROWS = [
  { kind: 'skill' as const, name: 'pdf-extract', path: 'skills/pdf-extract', score: 82, tier: 'green' as const, slug: 'a--b--skill-pdf-extract' },
  { kind: 'mcp_server' as const, name: 'payments', path: 'servers/payments', score: 47, tier: 'orange' as const, slug: 'a--b--mcp-server-payments' },
]

describe('ComponentScoresTable', () => {
  it('renders one deep-linked row per capability with a tier-derived chip', () => {
    const { container } = render(<ComponentScoresTable rows={ROWS} />)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', '/items/a--b--skill-pdf-extract')
    // green → all clear; orange → needs review (derived from tier)
    expect(screen.getByText('all clear')).toBeInTheDocument()
    expect(screen.getByText('needs review')).toBeInTheDocument()
    expect(container.querySelector('.ar-panel-lead')?.textContent).toContain('never fused')
  })

  it('renders the not-in-this-scan explainer panel when there are no capabilities', () => {
    const { container } = render(<ComponentScoresTable rows={[]} />)
    expect(container.querySelector('.ar-empty--na')).not.toBeNull()
    expect(screen.getByText('Behavior graded as one system.')).toBeInTheDocument()
    expect(container.querySelector('.cap-list')).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<ComponentScoresTable rows={ROWS} />)
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
