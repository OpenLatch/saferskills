import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import WhyRow from '../../../components/molecules/WhyRow'

describe('WhyRow', () => {
  it('renders index + tag + body in the .reason-row vocabulary', () => {
    const { container } = render(
      <WhyRow
        index="01"
        tag="verify"
        body={<>Every skill is scored against <b>five sub-rubrics</b>.</>}
      />,
    )
    expect(container.querySelector('.reason-row')).not.toBeNull()
    expect(container.querySelector('.reason-row .n')?.textContent).toBe('01')
    expect(container.querySelector('.reason-row .k')?.textContent?.startsWith('verify')).toBe(true)
    expect(screen.getByText('five sub-rubrics')).toBeInTheDocument()
  })

  it('renders the right-rail .ml-link when arrow is provided', () => {
    render(
      <WhyRow
        index="01"
        tag="find"
        body="Unified catalog."
        arrow={{ label: 'open methodology', href: '/methodology' }}
      />,
    )
    const link = screen.getByRole('link', { name: /open methodology/i })
    expect(link).toHaveAttribute('href', '/methodology')
  })

  it('renders meta lines as .stat spans', () => {
    const { container } = render(
      <WhyRow
        index="03"
        tag="verify"
        body="x"
        metaLines={[<><b>87</b>rules</>, 'updated hourly']}
      />,
    )
    expect(container.querySelectorAll('.reason-row .m .stat').length).toBe(2)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <WhyRow index="02" tag="monitor" body="On-push rescans + monthly deepscans." />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
