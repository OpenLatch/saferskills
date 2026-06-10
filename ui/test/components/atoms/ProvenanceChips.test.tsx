import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import ProvenanceChips from '../../../components/atoms/ProvenanceChips'

const CHIPS = [
  { label: 'OWASP Agentic', title: 'OWASP top 10' },
  { label: 'MITRE ATLAS', title: 'ATLAS techniques' },
  { label: 'Cloud-validated', title: 'ran on client', tone: 'tier' as const },
  { label: 'Apache-2.0', title: 'open source', tone: 'pack' as const },
]

describe('ProvenanceChips', () => {
  it('renders each chip with its tooltip + tone class', () => {
    const { container } = render(<ProvenanceChips chips={CHIPS} />)
    expect(screen.getByText('OWASP Agentic')).toHaveAttribute('title', 'OWASP top 10')
    expect(screen.getByText('Cloud-validated').className).toContain('tier')
    expect(screen.getByText('Apache-2.0').className).toContain('pack')
    expect(container.querySelectorAll('.prov-chip')).toHaveLength(4)
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<ProvenanceChips chips={CHIPS} />)
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
