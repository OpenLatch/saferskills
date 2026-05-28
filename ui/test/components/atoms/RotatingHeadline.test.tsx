import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RotatingHeadline from '../../../components/atoms/RotatingHeadline'

const NOUNS = ['Secrets Leaks', 'Prompt Injection', 'Supply-Chain Attacks', 'Tool Poisoning']

describe('RotatingHeadline', () => {
  it('renders the base + first noun by default', () => {
    render(<RotatingHeadline base="Every AI skill, audited against" nouns={NOUNS} />)
    expect(screen.getByText(/Every AI skill, audited against/)).toBeInTheDocument()
    expect(screen.getByText('Secrets Leaks')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <RotatingHeadline base="Audited against" nouns={NOUNS} respectsReducedMotion={false} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
