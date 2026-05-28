import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ScoreNumber from '../../../components/atoms/ScoreNumber'

describe('ScoreNumber', () => {
  it('renders value + slash + max', () => {
    render(<ScoreNumber value={87} />)
    expect(screen.getByText('87')).toBeInTheDocument()
    expect(screen.getByText('/100')).toBeInTheDocument()
  })

  it('respects a custom max', () => {
    render(<ScoreNumber value={42} max={50} />)
    expect(screen.getByText('/50')).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <div>
        <ScoreNumber value={95} size="hero" />
        <ScoreNumber value={48} size="md" />
      </div>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
