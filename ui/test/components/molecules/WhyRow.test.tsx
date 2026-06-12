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

  it('makes the whole row a single link to the arrow destination', () => {
    const { container } = render(
      <WhyRow
        index="01"
        tag="find"
        body="Unified catalog."
        arrow={{ label: 'open methodology', href: '/methodology' }}
      />,
    )
    const row = container.querySelector('a.reason-row')
    expect(row).not.toBeNull()
    expect(row).toHaveAttribute('href', '/methodology')
    // exactly one link target per row; the right-rail label is a visual cue
    expect(container.querySelectorAll('a').length).toBe(1)
    expect(container.querySelector('.ml-link')?.tagName).toBe('SPAN')
  })

  it('degrades to a plain div when no arrow is provided', () => {
    const { container } = render(<WhyRow index="02" tag="trust" body="x" />)
    const row = container.querySelector('.reason-row')
    expect(row?.tagName).toBe('DIV')
    expect(container.querySelector('a')).toBeNull()
  })

  it('renders real anchors per destination with `links` and keeps the root a div', () => {
    const { container } = render(
      <WhyRow
        index="05"
        tag="trust"
        body="No browser fingerprinting."
        links={[
          { label: 'privacy policy', href: '/privacy' },
          { label: 'methodology', href: '/methodology' },
        ]}
      />,
    )
    const row = container.querySelector('.reason-row')
    expect(row?.tagName).toBe('DIV')
    const anchors = container.querySelectorAll('a.ml-link')
    expect(anchors.length).toBe(2)
    expect(anchors[0]).toHaveAttribute('href', '/privacy')
    expect(anchors[1]).toHaveAttribute('href', '/methodology')
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
