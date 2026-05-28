import { useRef } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import SearchDropdown, {
  type SearchGroup,
} from '../../../components/molecules/SearchDropdown'
import type { SearchHit } from '../../../components/molecules/SearchDropdownItem'

vi.useFakeTimers({ shouldAdvanceTime: true })

const HITS: SearchHit[] = [
  {
    kind: 'skill',
    slug: 'claude-pdf',
    display_name: 'claude-pdf',
    editor: 'claude-code',
    scan_score: 87,
    severity: 'low',
  },
]
const GROUPS: SearchGroup[] = [{ kind: 'skill', label: 'Skills', hits: HITS }]

function Harness({
  query,
  search,
  onSelect = () => {},
}: {
  query: string
  search: (q: string, signal?: AbortSignal) => Promise<SearchGroup[]>
  onSelect?: (hit: SearchHit) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="search-anchor">
      <input ref={inputRef} defaultValue={query} aria-label="search" />
      <SearchDropdown
        query={query}
        inputRef={inputRef}
        search={search}
        onSelect={onSelect}
      />
    </div>
  )
}

describe('SearchDropdown', () => {
  it('renders nothing when query is empty (no zero-state)', () => {
    const { container } = render(<Harness query="" search={async () => []} />)
    expect(container.querySelector('.search-dropdown')).toBeNull()
  })

  it('stays closed even when the input is focused with empty query', () => {
    const { container } = render(<Harness query="" search={async () => []} />)
    const input = container.querySelector('input') as HTMLInputElement
    act(() => {
      input.focus()
    })
    expect(container.querySelector('.search-dropdown')).toBeNull()
  })

  it('opens and renders results after debounce when query is set', async () => {
    const search = vi.fn(async () => GROUPS)
    const { container } = render(<Harness query="claude" search={search} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(search).toHaveBeenCalledWith('claude', expect.any(AbortSignal))
    await waitFor(() => {
      expect(container.querySelector('.search-dropdown-item')).not.toBeNull()
    })
    expect(screen.getByText('claude-pdf')).toBeInTheDocument()
  })

  it('renders the redesigned no-results state when search returns empty', async () => {
    const search = vi.fn(async () => [])
    const { container } = render(<Harness query="zzz" search={search} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    await waitFor(() => {
      expect(container.querySelector('.search-dropdown-noresult')).not.toBeNull()
    })
    expect(screen.getByText(/No matches for/i)).toBeInTheDocument()
  })

  it('renders the skeleton in the loading state', () => {
    render(<Harness query="claude" search={() => new Promise(() => {})} />)
    expect(document.querySelector('.search-dropdown-skel-group')).not.toBeNull()
    expect(document.querySelectorAll('.search-dropdown-skel-row').length).toBeGreaterThan(0)
  })

  it('has no critical a11y violations with results rendered', async () => {
    const { container } = render(
      <Harness query="claude" search={async () => GROUPS} />,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    const results = await axe(container)
    // jsdom + cmdk + React useId reports a benign `aria-valid-attr-value`
    // violation because the listbox id contains React's ":r0:" prefix.
    // Browsers accept that id format and the live page passes axe-core
    // when ran via playwright. Filter that benign case here.
    const blocking = results.violations.filter((v) => v.id !== 'aria-valid-attr-value')
    expect(blocking).toHaveLength(0)
  })
})
