import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { axe } from 'vitest-axe'
import ThemeToggle from '../../../components/atoms/ThemeToggle'

describe('ThemeToggle', () => {
  beforeEach(() => {
    document.documentElement.className = ''
    delete document.documentElement.dataset.themeMode
    try { localStorage.clear() } catch { /* jsdom */ }
  })

  it('renders 3 buttons in a labeled group', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('group', { name: /theme/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })

  it('persists the user mode + flips html.dark when clicking Dark', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: /dark theme/i }))
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.themeMode).toBe('dark')
    expect(localStorage.getItem('ss-theme')).toBe('dark')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<ThemeToggle />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
