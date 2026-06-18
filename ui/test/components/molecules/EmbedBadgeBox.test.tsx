import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import EmbedBadgeBox from '../../../components/molecules/EmbedBadgeBox'

describe('EmbedBadgeBox', () => {
  it('renders the README terminal with the markdown snippet', () => {
    const { container } = render(
      <EmbedBadgeBox scanId="abc123" score={87} tier="green" slug="acme--foo" />,
    )
    expect(container.querySelector('.bt-title')?.textContent).toBe('README.md')
    const code = container.querySelector('.bt-body code')?.textContent ?? ''
    expect(code).toContain('SaferSkills 87/100')
    expect(code).toContain('badge/abc123/87.svg')
  })

  it('renders the tier-colored badge preview pill', () => {
    const { container } = render(
      <EmbedBadgeBox scanId="abc123" score={87} tier="green" slug="acme--foo" />,
    )
    const pill = container.querySelector('.badge-preview')
    expect(pill).not.toBeNull()
    expect(pill?.classList.contains('tier-green')).toBe(true)
    expect(pill?.textContent).toContain('87')
    expect(pill?.textContent).toContain('green')
  })

  it('falls back to unscored when no tier is given', () => {
    const { container } = render(<EmbedBadgeBox scanId="abc123" score={42} slug="acme--foo" />)
    const pill = container.querySelector('.badge-preview')
    expect(pill?.classList.contains('tier-unscoped')).toBe(true)
    expect(pill?.textContent).toContain('unscored')
  })

  it('calls onCopy with the format on each copy button', () => {
    const onCopy = vi.fn()
    render(<EmbedBadgeBox scanId="abc123" score={87} tier="green" slug="acme--foo" onCopy={onCopy} />)
    fireEvent.click(screen.getByRole('button', { name: /copy as html/i }))
    expect(onCopy).toHaveBeenCalledWith('html')
    fireEvent.click(screen.getByRole('button', { name: /copy to md/i }))
    expect(onCopy).toHaveBeenCalledWith('markdown')
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <EmbedBadgeBox scanId="abc123" score={87} tier="green" slug="acme--foo" />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })

  it('emits the agent badge + report paths under kind="agent"', () => {
    const { container } = render(
      <EmbedBadgeBox kind="agent" scanId="run9" score={10} tier="red" altPrefix="SaferSkills Agent" />,
    )
    const code = container.querySelector('.bt-body code')?.textContent ?? ''
    expect(code).toContain('badge/agent/run9/10.svg')
    expect(code).toContain('/agents/run9')
    expect(code).not.toContain('/scans/')
    expect(code).toContain('SaferSkills Agent 10/100')
  })
})
