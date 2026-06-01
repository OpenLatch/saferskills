import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import WeightBars from '../../../components/molecules/WeightBars'

const ROWS = [
  { label: 'Security', weight: 35, rules: 'SS-HOOKS-RCE-CURL-PIPE-01' },
  { label: 'Supply chain', weight: 20 },
  { label: 'Community', weight: 15 },
]

describe('WeightBars', () => {
  it('renders one .wb-row per weight with label + percent', () => {
    const { container } = render(<WeightBars rows={ROWS} />)
    const rows = container.querySelectorAll('.wb-row')
    expect(rows.length).toBe(3)
    expect(container.querySelector('.wb-name b')?.textContent).toBe('Security')
    expect([...container.querySelectorAll('.wb-wt')].map((e) => e.textContent)).toEqual([
      '35%',
      '20%',
      '15%',
    ])
  })

  it('sizes each fill via the --wb-frac scaleX custom property', () => {
    const { container } = render(<WeightBars rows={ROWS} />)
    const first = container.querySelector('.wb-fill') as HTMLElement
    expect(first.style.getPropertyValue('--wb-frac')).toBe('0.35')
  })

  it('renders the optional mono sub-label only when provided', () => {
    const { container } = render(<WeightBars rows={ROWS} />)
    expect(container.querySelectorAll('.wb-rule').length).toBe(1)
    expect(container.querySelector('.wb-rule')?.textContent).toBe('SS-HOOKS-RCE-CURL-PIPE-01')
  })

  it('drops the outer frame when framed={false}', () => {
    const { container } = render(<WeightBars rows={ROWS} framed={false} />)
    expect(container.querySelector('.weight-bars')?.classList.contains('weight-bars--bare')).toBe(
      true,
    )
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<WeightBars rows={ROWS} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
