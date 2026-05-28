import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Chip from '../../../components/atoms/Chip'

describe('Chip', () => {
  it('renders the label', () => {
    render(<Chip>scan tier</Chip>)
    expect(screen.getByText('scan tier')).toBeInTheDocument()
  })

  it('applies tier variants', () => {
    const { container } = render(<Chip variant="g">≥80</Chip>)
    expect(container.querySelector('.chip.g')).not.toBeNull()
  })

  it('is accessible across variants (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <Chip>default</Chip>
        <Chip variant="g">≥80</Chip>
        <Chip variant="y">60-79</Chip>
        <Chip variant="o">40-59</Chip>
        <Chip variant="r">&lt;40</Chip>
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
