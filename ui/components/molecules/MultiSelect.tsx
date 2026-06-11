import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

export interface MultiSelectOption {
  value: string
  label: string
  /** Optional leading affordance (e.g. a runtime monogram). */
  icon?: ReactNode
}

interface Props {
  /** Trigger label prefix (e.g. `Runtime`, `Findings`, `Period`). */
  label: string
  options: MultiSelectOption[]
  /** Currently-selected values. */
  selected: string[]
  /** Fired with the next selected set on every toggle / clear. */
  onChange: (next: string[]) => void
  /** Accessible name for the trigger + listbox. */
  ariaLabel: string
  className?: string
}

/**
 * MultiSelect — a keyboard-accessible multi-select listbox popover for the
 * `/agents` filter toolbar (I-5.6 §12.2). A DOM-rendered `aria-multiselectable`
 * listbox (NOT native `<select multiple>`, which can't carry the DS type stack /
 * icons). Trigger shows the label + a selected-count badge.
 *
 * A11y: trigger opens on Enter/Space/ArrowDown; the open list handles Up/Down/
 * Home/End to move the active option, Space/Enter to toggle, Escape to close.
 * Closes on outside-click + restores focus to the trigger. CSS (`.ms-*`) is in
 * `page-agent-directory.css`.
 */
export default function MultiSelect({
  label,
  options,
  selected,
  onChange,
  ariaLabel,
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

  function toggleValue(value: string) {
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

  const count = selected.length
  const optionId = (i: number) => `${listId}-opt-${i}`

  return (
    <div ref={rootRef} className={`ms ${className}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        className={`ms-btn ${count > 0 ? 'is-active' : ''}`.trim()}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKey}
      >
        <span className="ms-label">{label}</span>
        {count > 0 && <span className="ms-count">{count}</span>}
        <span className="ms-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div className="ms-panel">
          <ul
            ref={listRef}
            className="ms-list"
            role="listbox"
            aria-multiselectable="true"
            aria-label={ariaLabel}
            aria-activedescendant={optionId(activeIndex)}
            tabIndex={-1}
            onKeyDown={onListKey}
          >
            {options.map((opt, i) => {
              const isSelected = selected.includes(opt.value)
              return (
                <li
                  key={opt.value}
                  id={optionId(i)}
                  role="option"
                  aria-selected={isSelected}
                  className={`ms-opt ${i === activeIndex ? 'is-active' : ''} ${
                    isSelected ? 'is-selected' : ''
                  }`.trim()}
                  onClick={() => {
                    setActiveIndex(i)
                    toggleValue(opt.value)
                  }}
                >
                  <span className="ms-check" aria-hidden="true">
                    {isSelected ? '✓' : ''}
                  </span>
                  {opt.icon && <span className="ms-ic">{opt.icon}</span>}
                  <span className="ms-opt-label">{opt.label}</span>
                </li>
              )
            })}
          </ul>
          {count > 0 && (
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
