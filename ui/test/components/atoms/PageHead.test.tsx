import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import PageHead from '../../../components/atoms/PageHead'

describe('PageHead', () => {
  it('renders eyebrow + title + lede + path + meta pills', () => {
    render(
      <PageHead
        eyebrow="CATALOG · 01"
        title="The trusted catalog."
        lede="One score, one trail."
        path="/catalog"
        meta={[{ label: 'SORTED', value: 'most installed' }]}
      />,
    )
    expect(screen.getByText('CATALOG · 01')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('The trusted catalog.')
    expect(screen.getByText('One score, one trail.')).toBeInTheDocument()
    expect(screen.getByText('SORTED')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <PageHead eyebrow="SCAN · 02" title="Paste a public GitHub URL." path="/scan" />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
