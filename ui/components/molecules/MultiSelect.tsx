import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

export interface MultiSelectOption {
  /** Option value; the empty string means "no filter" (radio variant only). */
  value: string
  label: string
  /** Optional leading affordance (e.g. a runtime monogram / severity square). */
  icon?: ReactNode
}

interface Props {
  /** Trigger key prefix (e.g. `Period`, `Agent`, `Findings`). */
  label: string
  /** Trigger value shown when nothing is selected (e.g. `All time`, `All`, `Any`). */
  allLabel: string
  options: MultiSelectOption[]
  /** Currently-selected values. */
  selected: string[]
  /** Fired with the next selected set on every toggle / clear. */
  onChange: (next: string[]) => void
  /** Accessible name for the trigger + listbox. */
  ariaLabel: string
  /**
   * `check` (default) — multi-select checkboxes; `radio` — single-select presets
   * (the mockup Period/Sort `.pr-opt` rows; an empty-value option clears).
   */
  variant?: 'check' | 'radio'
  /** Render the leading checkbox square (check variant; the mockup Findings rows drop it). */
  showBox?: boolean
  className?: string
}

/**
 * MultiSelect — the `/agents` filter-toolbar dropdown (I-5.6 §12.2). Markup
 * mirrors the locked mockup `.ms` vocabulary: a `Key: Value ▾` trigger + a
 * popover panel of checkbox rows (`.box`/`.nm`) or single-select preset rows
 * (`.pr-opt`), with a Clear foot on the multi-select variants.
 *
 * A11y: a DOM-rendered `aria-multiselectable` listbox (NOT native `<select>`,
 * which can't carry the DS type stack / icons). Trigger opens on Enter/Space/
 * ArrowDown; the open list handles Up/Down/Home/End, Space/Enter to toggle,
 * Escape to close; closes on outside-click + restores focus. CSS (`.ms-*`) is
 * in `page-agent-directory.css`.
 */
export default function MultiSelect({
  label,
  allLabel,
  options,
  selected,
  onChange,
  ariaLabel,
  variant = 'check',
  showBox = true,
  className = '',
}: Props) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const listId = useId()

  useEffect(() => {
    if (open) listRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  function isSelected(value: string): boolean {
    if (variant === 'radio' && value === '') return selected.length === 0
    return selected.includes(value)
  }

  function toggleValue(value: string) {
    if (variant === 'radio') {
      onChange(value === '' ? [] : [value])
      close()
      return
    }
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  }

  function onTriggerKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setActiveIndex(0)
      setOpen(true)
    }
  }

  function onListKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault()
      close()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(options.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(0, i - 1))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActiveIndex(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      setActiveIndex(options.length - 1)
    } else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      const opt = options[activeIndex]
      if (opt) toggleValue(opt.value)
    }
  }

  // Trigger value: all-label when untouched, the option label when single,
  // `N selected` past that (mockup `updateMsLabel`).
  const count = selected.length
  const valueLabel =
    count === 0
      ? allLabel
      : count === 1
        ? (options.find((o) => o.value === selected[0])?.label ?? allLabel)
        : `${count} selected`
  const optionId = (i: number) => `${listId}-opt-${i}`

  return (
    <div ref={rootRef} className={`ms ${open ? 'open' : ''} ${className}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        className="ms-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKey}
      >
        <span className="k">{label}:</span> <b>{valueLabel}</b>{' '}
        <span className="car" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div className="ms-panel">
          <ul
            ref={listRef}
            className={`ms-list ${variant === 'radio' ? 'pr' : ''}`.trim()}
            role="listbox"
            aria-multiselectable={variant === 'check'}
            aria-label={ariaLabel}
            aria-activedescendant={optionId(activeIndex)}
            tabIndex={-1}
            onKeyDown={onListKey}
          >
            {options.map((opt, i) => {
              const on = isSelected(opt.value)
              return (
                <li
                  key={opt.value}
                  id={optionId(i)}
                  role="option"
                  aria-selected={on}
                  className={`ms-opt ${variant === 'radio' ? 'pr-opt' : ''} ${
                    i === activeIndex ? 'is-active' : ''
                  } ${on ? 'is-selected' : ''}`
                    .replace(/\s+/g, ' ')
                    .trim()}
                  onClick={() => {
                    setActiveIndex(i)
                    toggleValue(opt.value)
                  }}
                >
                  {variant === 'check' && showBox && <span className="box" aria-hidden="true" />}
                  {opt.icon}
                  <span className="nm">{opt.label}</span>
                </li>
              )
            })}
          </ul>
          {variant === 'check' && (
            <div className="ms-foot">
              <button type="button" className="ms-clear" onClick={() => onChange([])}>
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
