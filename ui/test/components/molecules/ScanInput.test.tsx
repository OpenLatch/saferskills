import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ScanInput from '../../../components/molecules/ScanInput'

describe('ScanInput', () => {
  it('renders the github.com prefix + input + submit button', () => {
    const { container } = render(<ScanInput />)
    expect(container.querySelector('.scan-input')).not.toBeNull()
    expect(container.querySelector('.scan-input-prefix')?.textContent).toBe('github.com/')
    expect(screen.getByLabelText('Repository path')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /scan now/i })).toBeInTheDocument()
  })

  it('renders inline error text when provided', () => {
    render(<ScanInput error="Bad URL" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Bad URL')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ScanInput initialValue="anthropics/skills" />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
