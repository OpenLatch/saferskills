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

  it('single-line base renders no .rh-line blocks (backward-compatible)', () => {
    const { container } = render(
      <RotatingHeadline base="Every AI capability, audited against" nouns={NOUNS} />,
    )
    expect(container.querySelector('.rh-line')).toBeNull()
  })

  it('appends the trailing static text outside the rotator', () => {
    const { container } = render(
      <RotatingHeadline base="Audited against" nouns={['Prompt Injection']} trailing="." />,
    )
    // The h1 should end with a period after the rotator
    const h1 = container.querySelector('h1')!
    expect(h1.textContent?.endsWith('.')).toBe(true)
  })

  it('baseLines renders one .rh-line block per entry, rotator inside the last', () => {
    const { container } = render(
      <RotatingHeadline
        baseLines={['Audit every capability.', 'Scan the whole agent against']}
        nouns={NOUNS}
        trailing="."
      />,
    )
    const lines = container.querySelectorAll('.rh-line')
    expect(lines).toHaveLength(2)
    expect(lines[0]?.textContent).toBe('Audit every capability.')
    // The last line hosts the rotator (and trailing) inline.
    expect(lines[0]?.querySelector('.rotator')).toBeNull()
    expect(lines[1]?.querySelector('.rotator-word')?.textContent).toBe('Secrets Leaks')
    expect(lines[1]?.textContent?.endsWith('.')).toBe(true)
    expect(lines[1]?.textContent).toContain('Scan the whole agent against')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <RotatingHeadline base="Audited against" nouns={NOUNS} respectsReducedMotion={false} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })

  it('baseLines variant is accessible (vitest-axe)', async () => {
    const { container } = render(
      <RotatingHeadline
        baseLines={['Audit every capability.', 'Scan the whole agent against']}
        nouns={NOUNS}
        trailing="."
        respectsReducedMotion={false}
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
