import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import PageHead from '../../../components/atoms/PageHead'

describe('PageHead', () => {
  it('renders eyebrow + title + lede', () => {
    render(
      <PageHead
        eyebrow="CATALOG · 01"
        title="The trusted catalog."
        lede="One score, one trail."
      />,
    )
    expect(screen.getByText('CATALOG · 01')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('The trusted catalog.')
    expect(screen.getByText('One score, one trail.')).toBeInTheDocument()
  })

  it('omits the lede when not provided', () => {
    const { container } = render(<PageHead eyebrow="SCAN · 02" title="Paste a public GitHub URL." />)
    expect(container.querySelector('.ph-lede')).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <PageHead eyebrow="SCAN · 02" title="Paste a public GitHub URL." />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
