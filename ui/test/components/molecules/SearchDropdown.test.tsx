import { useRef } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  {
    kind: 'skill',
    slug: 'github-mcp',
    display_name: 'github-mcp',
    editor: 'cursor',
    scan_score: 72,
    severity: 'medium',
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

/** Render the harness, advance past the 300ms debounce, and wait for the two
 *  result rows to mount. Returns the host input for keyboard-driven cases. */
async function renderReady(onSelect?: (hit: SearchHit) => void) {
  const search = vi.fn(async () => GROUPS)
  const utils = render(<Harness query="claude" search={search} onSelect={onSelect} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400)
  })
  await waitFor(() => {
    expect(utils.container.querySelectorAll('.search-dropdown-item').length).toBe(2)
  })
  const input = utils.container.querySelector('input') as HTMLInputElement
  const items = () =>
    utils.container.querySelectorAll<HTMLElement>('.search-dropdown-item')
  return { ...utils, input, items }
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

  it('does not preselect any row when results first load (Linear/Algolia model)', async () => {
    const { container } = await renderReady()
    expect(
      container.querySelector(".search-dropdown-item[data-selected='true']"),
    ).toBeNull()
    const input = container.querySelector('input') as HTMLInputElement
    expect(input.getAttribute('aria-activedescendant')).toBeNull()
  })

  it('ArrowDown highlights the first row and wires aria-activedescendant', async () => {
    const { input, items } = await renderReady()
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    await waitFor(() => {
      expect(items()[0].getAttribute('data-selected')).toBe('true')
    })
    expect(input.getAttribute('aria-activedescendant')).toBeTruthy()
  })

  it('ArrowDown/ArrowUp move the active row and wrap at both ends', async () => {
    const { input, items } = await renderReady()
    fireEvent.keyDown(input, { key: 'ArrowDown' }) // none → first
    await waitFor(() => expect(items()[0].getAttribute('data-selected')).toBe('true'))
    fireEvent.keyDown(input, { key: 'ArrowDown' }) // first → second
    await waitFor(() => expect(items()[1].getAttribute('data-selected')).toBe('true'))
    fireEvent.keyDown(input, { key: 'ArrowUp' }) // second → first
    await waitFor(() => expect(items()[0].getAttribute('data-selected')).toBe('true'))
    fireEvent.keyDown(input, { key: 'ArrowUp' }) // first → wraps to last
    await waitFor(() => expect(items()[1].getAttribute('data-selected')).toBe('true'))
  })

  it('Enter on a highlighted row calls onSelect with that hit', async () => {
    const onSelect = vi.fn()
    const { input } = await renderReady(onSelect)
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith(HITS[0])
  })

  it('Enter with no row highlighted does not call onSelect (keeps the fallback path)', async () => {
    const onSelect = vi.fn()
    const { input } = await renderReady(onSelect)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('Escape closes the dropdown', async () => {
    const { container, input } = await renderReady()
    expect(container.querySelector('.search-dropdown')).not.toBeNull()
    fireEvent.keyDown(input, { key: 'Escape' })
    await waitFor(() => {
      expect(container.querySelector('.search-dropdown')).toBeNull()
    })
  })

  it('does not preselect a row after the query changes (requery clears the highlight)', async () => {
    const groupsA: SearchGroup[] = [{ kind: 'skill', label: 'Skills', hits: [HITS[0]] }]
    const groupsB: SearchGroup[] = [{ kind: 'skill', label: 'Skills', hits: [HITS[1]] }]
    const search = vi.fn(async (q: string) => (q === 'a' ? groupsA : groupsB))
    const { container, rerender } = render(<Harness query="a" search={search} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    const input = container.querySelector('input') as HTMLInputElement
    // Highlight the only row, then change the query → fresh results must not
    // inherit the old highlight (and cmdk must not auto-select row 0).
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    await waitFor(() =>
      expect(container.querySelector(".search-dropdown-item[data-selected='true']")).not.toBeNull(),
    )
    rerender(<Harness query="b" search={search} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    await waitFor(() => {
      expect(screen.getByText('github-mcp')).toBeInTheDocument()
    })
    expect(
      container.querySelector(".search-dropdown-item[data-selected='true']"),
    ).toBeNull()
  })
})
