import type { Story } from '@ladle/react'
import { useRef, useState } from 'react'
import SearchDropdown, {
  type SearchGroup,
} from '../../components/molecules/SearchDropdown'
import type { SearchHit } from '../../components/molecules/SearchDropdownItem'

const MOCK_HITS: SearchHit[] = [
  {
    kind: 'skill',
    slug: 'claude-pdf',
    display_name: 'claude-pdf',
    editor: 'claude-code',
    scan_score: 87,
    severity: 'low',
  },
  {
    kind: 'skill',
    slug: 'claude-excel',
    display_name: 'claude-excel',
    editor: 'claude-code',
    scan_score: 42,
    severity: 'high',
  },
  {
    kind: 'mcp_server',
    slug: 'github-mcp',
    display_name: 'github-mcp',
    editor: 'cursor',
    scan_score: 28,
    severity: 'critical',
  },
  {
    kind: 'mcp_server',
    slug: 'linear-mcp',
    display_name: 'linear-mcp',
    editor: 'claude-code',
    scan_score: 91,
    severity: 'info',
  },
  {
    kind: 'hook',
    slug: 'pre-commit-guard',
    display_name: 'pre-commit-guard',
    editor: 'claude-code',
    scan_score: 76,
    severity: 'medium',
  },
]

const GROUPS: SearchGroup[] = [
  { kind: 'skill', label: 'Skills', hits: MOCK_HITS.filter((h) => h.kind === 'skill') },
  { kind: 'mcp_server', label: 'MCP Servers', hits: MOCK_HITS.filter((h) => h.kind === 'mcp_server') },
  { kind: 'hook', label: 'Hooks', hits: MOCK_HITS.filter((h) => h.kind === 'hook') },
]

function Frame({
  query,
  search,
}: {
  query: string
  search: (q: string, signal?: AbortSignal) => Promise<SearchGroup[]>
}) {
  const [value, setValue] = useState(query)
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div style={{ width: 480, padding: 40, fontFamily: 'var(--font-sans)' }}>
      <div className="search-anchor">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Search the catalog…"
          style={{
            width: '100%',
            padding: '12px 14px',
            border: '1px solid var(--color-ink)',
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            background: 'var(--color-paper)',
          }}
        />
        <SearchDropdown
          query={value}
          inputRef={inputRef}
          search={search}
          onSelect={(hit) => console.log('selected', hit)}
        />
      </div>
    </div>
  )
}

export const WithResults: Story = () => (
  <Frame
    query="claude"
    search={async (q) =>
      GROUPS.map((g) => ({
        ...g,
        hits: g.hits.filter((h) => h.display_name.includes(q)),
      })).filter((g) => g.hits.length > 0)
    }
  />
)

export const NoResults: Story = () => (
  <Frame query="zzzzz" search={async () => []} />
)

export const Loading: Story = () => (
  <Frame query="claude" search={() => new Promise(() => {})} />
)

export const ErrorState: Story = () => (
  <Frame
    query="claude"
    search={async () => {
      throw new Error('boom')
    }}
  />
)
