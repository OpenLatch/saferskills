import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import Input from '../../../components/atoms/Input'

describe('Input', () => {
  it('renders the prefix glyph', () => {
    const { container } = render(
      <Input prefix="github.com/" placeholder="org/repo" aria-label="Repo URL" />,
    )
    expect(container.querySelector('.input .glyph')?.textContent).toBe('github.com/')
  })

  it('forwards onChange', () => {
    let value = ''
    render(
      <Input
        aria-label="Email"
        placeholder="you@example.com"
        onChange={(e) => { value = e.target.value }}
      />,
    )
    const field = screen.getByPlaceholderText('you@example.com')
    fireEvent.change(field, { target: { value: 'a@b.c' } })
    expect(value).toBe('a@b.c')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <Input prefix="github.com/" placeholder="org/repo" aria-label="Repo URL" />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
