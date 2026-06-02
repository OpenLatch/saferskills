import { render, screen } from '@testing-library/react'
import { Command } from 'cmdk'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import SearchDropdownItem, {
  type SearchHit,
} from '../../../components/molecules/SearchDropdownItem'

const HIT: SearchHit = {
  kind: 'skill',
  slug: 'claude-pdf',
  display_name: 'claude-pdf',
  editor: 'claude-code',
  scan_score: 87,
  severity: 'low',
}

// cmdk's `Command.Item` requires a `Command` + `Command.List` ancestor.
function wrap(hit: SearchHit) {
  return (
    <div className="search-dropdown">
      <Command shouldFilter={false} label="Catalog search">
        <Command.List>
          <Command.Group heading="Skills">
            <SearchDropdownItem hit={hit} onSelect={() => {}} id="opt-1" />
          </Command.Group>
        </Command.List>
      </Command>
    </div>
  )
}

describe('SearchDropdownItem', () => {
  it('renders name, editor, severity label + score', () => {
    const { container } = render(wrap(HIT))
    expect(container.querySelector('.search-dropdown-item')).not.toBeNull()
    expect(screen.getByText('claude-pdf')).toBeInTheDocument()
    expect(screen.getByText('claude-code')).toBeInTheDocument()
    expect(container.querySelector('.search-dropdown-meta.sev-low')).not.toBeNull()
    expect(container.querySelector('.sev-label')?.textContent).toBe('low')
    expect(container.querySelector('.sev-score')?.textContent).toBe('87')
  })

  it('reflects severity in the meta-pill class', () => {
    const { container } = render(wrap({ ...HIT, severity: 'critical', scan_score: 12 }))
    expect(container.querySelector('.search-dropdown-meta.sev-critical')).not.toBeNull()
    expect(container.querySelector('.sev-score')?.textContent).toBe('12')
  })

  it('has no critical a11y violations', async () => {
    const { container } = render(wrap(HIT))
    const results = await axe(container)
    // jsdom + cmdk + React useId reports a benign `aria-valid-attr-value`
    // violation because the listbox id contains React's ":r0:" prefix;
    // browsers accept that id format. Filter it as SearchDropdown.test does.
    const blocking = results.violations.filter((v) => v.id !== 'aria-valid-attr-value')
    expect(blocking).toHaveLength(0)
  })
})
