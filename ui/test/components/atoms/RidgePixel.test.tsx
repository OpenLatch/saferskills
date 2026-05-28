import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RidgePixel from '../../../components/atoms/RidgePixel'

describe('RidgePixel', () => {
  it('renders the dark-slate divider shell', () => {
    const { container } = render(<RidgePixel />)
    expect(container.querySelector('.ridge.ridge-pixel')).not.toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<RidgePixel label="— INSTALL —" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
