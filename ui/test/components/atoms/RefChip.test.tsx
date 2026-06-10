import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import RefChip from '../../../components/atoms/RefChip'

describe('RefChip', () => {
  it('renders an external deep-link with the tinted family class', () => {
    render(<RefChip label="ASI04:2026" href="https://genai.owasp.org/" kind="owasp" />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://genai.owasp.org/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(link.className).toContain('owasp')
    expect(screen.getByText('ASI04:2026')).toBeInTheDocument()
  })

  it('tints the MITRE family differently', () => {
    render(<RefChip label="AML.T0053" href="https://atlas.mitre.org/" kind="mitre" />)
    expect(screen.getByRole('link').className).toContain('mitre')
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <RefChip label="NIST AI 600-1" href="https://www.nist.gov/" kind="nist" />
    )
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
