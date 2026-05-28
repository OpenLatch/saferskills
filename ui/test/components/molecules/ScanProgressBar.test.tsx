import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ScanProgressBar from '../../../components/molecules/ScanProgressBar'

describe('ScanProgressBar', () => {
  it('renders a progressbar with correct aria-valuenow', () => {
    const { container } = render(
      <ScanProgressBar completionPct={62} progressLabel="9 / 14 detectors complete" />,
    )
    const bar = container.querySelector('[role="progressbar"]')
    expect(bar?.getAttribute('aria-valuenow')).toBe('62')
    expect(container.querySelector('.progress-bar-fill')).not.toBeNull()
  })

  it('clamps completion to 0-100', () => {
    const { container } = render(<ScanProgressBar completionPct={150} />)
    expect(container.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('100')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ScanProgressBar completionPct={40} progressLabel="test" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
