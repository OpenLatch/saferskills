import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import TrustTierPill from '../../../components/atoms/TrustTierPill'

describe('TrustTierPill', () => {
  it('humanizes + joins the labels', () => {
    render(<TrustTierPill labels={['cloud-validated', 'client-administered']} />)
    expect(screen.getByText('Cloud-validated · Client-administered')).toBeInTheDocument()
  })

  it('is keyboard-focusable and describes itself with a tooltip', () => {
    const { container } = render(
      <TrustTierPill labels={['cloud-validated']} tipId="tt" tooltip="ran on its own machine" />,
    )
    const pill = container.querySelector('.trust-pill') as HTMLElement
    expect(pill.getAttribute('tabindex')).toBe('0')
    expect(pill.getAttribute('aria-describedby')).toBe('tt')
    expect(container.querySelector('#tt')?.getAttribute('role')).toBe('tooltip')
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<TrustTierPill labels={['cloud-validated', 'client-administered']} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
