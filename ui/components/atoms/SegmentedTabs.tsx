import { type KeyboardEvent, useRef } from 'react'

export interface SegmentedTab {
  id: string
  label: string
  count?: number | string
  /** Active-state accent for the `segmented` variant. Default teal. */
  accent?: 'teal' | 'orange'
}

interface SegmentedTabsProps {
  tabs: SegmentedTab[]
  value: string
  onChange: (id: string) => void
  ariaLabel: string
  /** `underline` = the `/items/<slug>` tab look; `segmented` = the boxed /scan control. */
  variant?: 'underline' | 'segmented'
  /** Namespaces the generated tab/panel ids; pair with `panelId(idBase, tab.id)` on the panel. */
  idBase?: string
}

/** The panel id a tab points at via `aria-controls` — render this on the matching tabpanel. */
export function panelId(idBase: string, tabId: string): string {
  return `${idBase}-panel-${tabId}`
}

/**
 * Accessible segmented control with roving tabindex (←/→ move focus, Home/End,
 * Enter/Space activate). Two visual variants share one keyboard model:
 *  - `underline` adopts the `.sk-tabs/.sk-tab` token styling (lifted into the DS),
 *  - `segmented` is the boxed `.seg/.seg-tab` control with a per-tab teal/orange accent.
 */
export default function SegmentedTabs({
  tabs,
  value,
  onChange,
  ariaLabel,
  variant = 'segmented',
  idBase = 'seg',
}: SegmentedTabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  function focusTab(i: number) {
    const n = tabs.length
    refs.current[((i % n) + n) % n]?.focus()
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    switch (e.key) {
      case 'ArrowLeft':
        e.preventDefault()
        focusTab(i - 1)
        break
      case 'ArrowRight':
        e.preventDefault()
        focusTab(i + 1)
        break
      case 'Home':
        e.preventDefault()
        focusTab(0)
        break
      case 'End':
        e.preventDefault()
        focusTab(tabs.length - 1)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        onChange(tabs[i].id)
        break
    }
  }

  const listClass = variant === 'underline' ? 'sk-tabs' : 'seg'
  const tabClass = variant === 'underline' ? 'sk-tab' : 'seg-tab'

  return (
    <div className={listClass} role="tablist" aria-label={ariaLabel}>
      {tabs.map((t, i) => {
        const selected = t.id === value
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="tab"
            id={`${idBase}-tab-${t.id}`}
            aria-selected={selected}
            aria-controls={panelId(idBase, t.id)}
            tabIndex={selected ? 0 : -1}
            data-accent={t.accent === 'orange' ? 'orange' : undefined}
            className={`${tabClass}${selected ? ' on' : ''}`}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
            {t.count != null && <span className="t-ct">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
