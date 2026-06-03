import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import CheckGroupList, {
  type CheckGroupCategory,
  type CheckGroupFinding,
} from '../../../components/molecules/CheckGroupList'

const CATEGORIES: CheckGroupCategory[] = [
  { key: 'security', name: 'Security' },
  { key: 'maintenance', name: 'Maintenance' },
]
const SUB = { security: 40, maintenance: 90 }

describe('CheckGroupList', () => {
  it('renders a green pass row for an empty category', () => {
    const { container } = render(
      <CheckGroupList categories={CATEGORIES} subScores={SUB} findings={[]} emptyScanNoun="the latest scan" />,
    )
    const passRows = container.querySelectorAll('.chk-row.pass')
    expect(passRows.length).toBe(2)
    expect(passRows[0].querySelector('.chk-st')?.textContent).toBe('✓')
    expect(screen.getByText('All security checks passed')).toBeInTheDocument()
    // both categories are empty → the noun appears once per category
    expect(screen.getAllByText('No findings in this category for the latest scan.')).toHaveLength(2)
  })

  it('uses the ✕ fail glyph for high/critical and ⚠ warn for the rest', () => {
    const findings: CheckGroupFinding[] = [
      { id: 'a', ruleId: 'SS-A-01', severity: 'critical', subScore: 'security', filePath: 'a.sh', lineStart: 1 },
      { id: 'b', ruleId: 'SS-B-01', severity: 'medium', subScore: 'security', filePath: 'b.json', lineStart: 2 },
    ]
    const { container } = render(
      <CheckGroupList categories={CATEGORIES} subScores={SUB} findings={findings} />,
    )
    const fail = container.querySelector('.chk-row.fail')
    const warn = container.querySelector('.chk-row.warn')
    expect(fail?.querySelector('.chk-st')?.textContent).toBe('✕')
    expect(fail?.querySelector('.chk-id')?.textContent).toBe('SS-A-01')
    expect(warn?.querySelector('.chk-st')?.textContent).toBe('⚠')
    // maintenance has no findings → still a pass row
    expect(container.querySelectorAll('.chk-row.pass').length).toBe(1)
  })

  it('shows the flagged count in the head from findings.length', () => {
    const findings: CheckGroupFinding[] = [
      { id: 'a', ruleId: 'SS-A-01', severity: 'high', subScore: 'security', filePath: 'a.sh', lineStart: 1 },
    ]
    render(<CheckGroupList categories={CATEGORIES} subScores={SUB} findings={findings} />)
    expect(screen.getByText(/Findings & checks · 1 flagged/)).toBeInTheDocument()
  })

  it('defaults the empty-scan noun to "this scan"', () => {
    render(<CheckGroupList categories={[{ key: 'security', name: 'Security' }]} subScores={SUB} findings={[]} />)
    expect(screen.getByText('No findings in this category for this scan.')).toBeInTheDocument()
  })

  it('renders the renderCategoryFindings slot for a flagged category', () => {
    const findings: CheckGroupFinding[] = [
      { id: 'a', ruleId: 'SS-A-01', severity: 'high', subScore: 'security', filePath: 'a.sh', lineStart: 1 },
    ]
    const { container } = render(
      <CheckGroupList
        categories={CATEGORIES}
        subScores={SUB}
        findings={findings}
        renderCategoryFindings={(key) => (
          <div data-testid="slot" data-key={key}>
            slot
          </div>
        )}
      />,
    )
    // security has a finding → slot replaces the compact warn/fail rows
    expect(screen.getByTestId('slot')).toHaveAttribute('data-key', 'security')
    expect(container.querySelector('.chk-row.fail')).toBeNull()
    expect(container.querySelector('.chk-row.warn')).toBeNull()
    // maintenance is empty → still a green pass row
    expect(container.querySelectorAll('.chk-row.pass').length).toBe(1)
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(
      <CheckGroupList categories={CATEGORIES} subScores={SUB} findings={[]} />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
