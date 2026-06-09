import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import FrameworkBadges, { type FrameworkRef } from '../../../components/atoms/FrameworkBadges'

const refs: FrameworkRef[] = [
  { family: 'owasp-llm', id: 'LLM06', label: 'Excessive Agency', url: 'https://genai.owasp.org/x' },
  { family: 'mitre-atlas', id: 'AML.T0050', label: 'Command and Scripting Interpreter', url: 'https://atlas.mitre.org/y' },
  { family: 'cwe', id: 'CWE-78', label: 'OS Command Injection', url: 'https://cwe.mitre.org/z' },
]

describe('FrameworkBadges', () => {
  it('renders one badge per ref with family-prefixed id', () => {
    render(<FrameworkBadges frameworks={refs} />)
    expect(screen.getByText('LLM06')).toBeInTheDocument()
    expect(screen.getByText('OWASP')).toBeInTheDocument()
    expect(screen.getByText('ATLAS')).toBeInTheDocument()
    // CWE id already carries its prefix, so no separate family tag.
    expect(screen.getByText('CWE-78')).toBeInTheDocument()
    expect(screen.queryByText('CWE')).not.toBeInTheDocument()
  })

  it('links each badge out to its canonical reference', () => {
    render(<FrameworkBadges frameworks={[refs[0]]} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://genai.owasp.org/x')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer noopener')
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<FrameworkBadges frameworks={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(<FrameworkBadges frameworks={refs} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
