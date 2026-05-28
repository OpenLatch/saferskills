import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import RidgeFlow from '../../../components/atoms/RidgeFlow'

describe('RidgeFlow', () => {
  it('renders the divider shell', () => {
    const { container } = render(<RidgeFlow />)
    expect(container.querySelector('.ridge.ridge-flow')).not.toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<RidgeFlow label="— TRENDING —" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
