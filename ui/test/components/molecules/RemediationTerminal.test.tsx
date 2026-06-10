import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import RemediationTerminal from '../../../components/molecules/RemediationTerminal'

describe('RemediationTerminal', () => {
  it('renders the action, steps and a diff-colored safer-pattern snippet', () => {
    const { container } = render(
      <RemediationTerminal
        action="Strip embedded directives at registration."
        steps={['Strip directives.', 'Narrow scope.']}
        saferPattern={{ before: 'hidden directive', after: 'plain description' }}
      />
    )
    expect(screen.getByText('Strip embedded directives at registration.')).toBeInTheDocument()
    expect(container.querySelectorAll('.ar-rem-steps li')).toHaveLength(2)
    expect(container.querySelector('.at-body .del')?.textContent).toContain('hidden directive')
    expect(container.querySelector('.at-body .add')?.textContent).toContain('plain description')
  })

  it('renders steps only when there is no safer pattern', () => {
    const { container } = render(
      <RemediationTerminal action="Do the thing." steps={['One.']} saferPattern={null} />
    )
    expect(container.querySelector('.ar-term')).toBeNull()
  })

  it('flips Copy → Copied on click', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
    render(
      <RemediationTerminal
        action="Fix it."
        saferPattern={{ before: 'a', after: 'b' }}
        copyText="the fix"
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('the fix')
    expect(await screen.findByText('Copied')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <RemediationTerminal
        action="Fix it."
        steps={['One.']}
        saferPattern={{ before: 'a', after: 'b' }}
      />
    )
    expect((await axe(container)).violations).toHaveLength(0)
  })
})
