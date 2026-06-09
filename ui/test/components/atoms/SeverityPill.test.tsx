import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import SeverityPill from '../../../components/atoms/SeverityPill'

describe('SeverityPill', () => {
  it('defaults the label to the upper-cased severity', () => {
    render(<SeverityPill severity="critical" />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('respects an explicit label override', () => {
    render(<SeverityPill severity="high" label="HIGH RISK" />)
    expect(screen.getByText('HIGH RISK')).toBeInTheDocument()
  })

  it('applies the severity class for tinting', () => {
    const { container } = render(<SeverityPill severity="medium" />)
    const pill = container.querySelector('.sev')
    expect(pill).toHaveClass('sev', 'medium')
  })

  it('is accessible across the severity ladder (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <SeverityPill severity="critical" />
        <SeverityPill severity="high" />
        <SeverityPill severity="medium" />
        <SeverityPill severity="low" />
        <SeverityPill severity="info" />
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
