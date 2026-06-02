import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RotatingHeadline from '../../../components/atoms/RotatingHeadline'

const NOUNS = ['Secrets Leaks', 'Prompt Injection', 'Supply-Chain Attacks', 'Tool Poisoning']

describe('RotatingHeadline', () => {
  it('renders the base + first noun inside .rotator > .rotator-word', () => {
    const { container } = render(
      <RotatingHeadline base="Every AI capability, audited against" nouns={NOUNS} />,
    )
    expect(screen.getByText(/Every AI capability, audited against/)).toBeInTheDocument()
    expect(container.querySelector('.rotator')).not.toBeNull()
    expect(container.querySelector('.rotator-word')?.textContent).toBe('Secrets Leaks')
  })

  it('appends the trailing static text outside the rotator', () => {
    const { container } = render(
      <RotatingHeadline base="Audited against" nouns={['Prompt Injection']} trailing="." />,
    )
    // The h1 should end with a period after the rotator
    const h1 = container.querySelector('h1')!
    expect(h1.textContent?.endsWith('.')).toBe(true)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <RotatingHeadline base="Audited against" nouns={NOUNS} respectsReducedMotion={false} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
