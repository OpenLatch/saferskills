import type { Story } from '@ladle/react'
import { Command } from 'cmdk'
import SearchDropdownItem, {
  type SearchHit,
} from '../../components/molecules/SearchDropdownItem'

// SearchDropdownItem renders a cmdk `Command.Item`, which requires a
// `Command` + `Command.List` ancestor — the same nesting `SearchDropdown`
// provides at runtime. The `.search-dropdown` wrapper supplies the row chrome.
function Frame({ hits }: { hits: SearchHit[] }) {
  return (
    <div style={{ width: 480, padding: 40, fontFamily: 'var(--font-sans)' }}>
      <div className="search-dropdown" data-state="open">
        <Command shouldFilter={false} label="Catalog search">
          <Command.List>
            <Command.Group heading="Skills" className="search-dropdown-group">
              {hits.map((hit) => (
                <SearchDropdownItem
                  key={`${hit.kind}:${hit.slug}`}
                  hit={hit}
                  onSelect={(h) => console.log('selected', h)}
                  id={`opt-${hit.kind}-${hit.slug}`}
                />
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  )
}

const HITS: SearchHit[] = [
  {
    kind: 'skill',
    slug: 'claude-pdf',
    display_name: 'claude-pdf',
    editor: 'claude-code',
    scan_score: 91,
    severity: 'info',
  },
  {
    kind: 'skill',
    slug: 'claude-excel',
    display_name: 'claude-excel',
    editor: 'claude-code',
    scan_score: 76,
    severity: 'medium',
  },
  {
    kind: 'skill',
    slug: 'risky-skill',
    display_name: 'risky-skill',
    editor: 'cursor',
    scan_score: 28,
    severity: 'critical',
  },
]

export const SeverityLadder: Story = () => <Frame hits={HITS} />

export const SingleLow: Story = () => (
  <Frame
    hits={[
      {
        kind: 'skill',
        slug: 'claude-pdf',
        display_name: 'claude-pdf',
        editor: 'claude-code',
        scan_score: 87,
        severity: 'low',
      },
    ]}
  />
)
