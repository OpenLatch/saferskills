import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import WhyRow from '../../../components/molecules/WhyRow'

describe('WhyRow', () => {
  it('renders index + tag + body', () => {
    render(
      <WhyRow
        index="01"
        tag="verify"
        body={<>Every skill is scored against <b>five sub-rubrics</b>.</>}
      />,
    )
    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('verify')).toBeInTheDocument()
    expect(screen.getByText('five sub-rubrics')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <WhyRow index="02" tag="monitor" body="On-push rescans + monthly deepscans." />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
