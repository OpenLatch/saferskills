import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Button from '../../../components/atoms/Button'
import ButtonPair from '../../../components/atoms/ButtonPair'

describe('ButtonPair', () => {
  it('renders two children inside a .btn-pair shell', () => {
    const { container } = render(
      <ButtonPair>
        <Button variant="primary">A</Button>
        <Button>B</Button>
      </ButtonPair>,
    )
    expect(container.querySelector('.btn-pair')).not.toBeNull()
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <ButtonPair>
        <Button variant="primary">A</Button>
        <Button>B</Button>
      </ButtonPair>,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
