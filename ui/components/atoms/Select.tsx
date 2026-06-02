import { useEffect, useId, useRef, useState } from 'react'

export interface SelectOption {
  value: string
  label: string
}

interface Props {
  /** Currently selected value. */
  value: string
  /** Options in display order. */
  options: SelectOption[]
  /** Fired with the chosen value when the user commits a selection. */
  onChange: (value: string) => void
  /** Accessible name for both the trigger and the listbox. */
  ariaLabel: string
  /** Extra class on the root (e.g. a page-scoped width tweak). */
  className?: string
}

/**
 * DS single-select dropdown — a DOM-rendered listbox (NOT a native `<select>`).
 *
 * Why not `<select>`: the browser renders a native `<option>` popup with the OS
 * font, ignoring our `@fontsource` web fonts — so the open list never matches
 * the design system. Rendering the menu in the DOM keeps the DS type stack
 * (Space Mono / DM Sans), tokens, dark mode, and the unroll animation.
 *
 * A11y: WAI-ARIA listbox with `aria-activedescendant` (focus stays on the
 * listbox). Trigger opens on Enter/Space/Arrow; the open list handles
 * Up/Down/Home/End to move, Enter/Space to commit, Escape to close. Closes on
 * outside-click and restores focus to the trigger after a commit.
 */
export default function Select({ value, options, onChange, ariaLabel, className }: Props) {
  const [open, setOpen] = useState(false)
  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  )
  const [activeIndex, setActiveIndex] = useState(selectedIndex)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const listId = useId()
  const selected = options[selectedIndex] ?? options[0]

  // On open, point the active descendant at the current value + focus the list.
  useEffect(() => {
    if (!open) return
    setActiveIndex(selectedIndex)
    listRef.current?.focus()
  }, [open, selectedIndex])

  // Outside-click closes.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  function commit(index: number) {
    const opt = options[index]
    if (opt) onChange(opt.value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  function onTriggerKeyDown(e: React.KeyboardEvent) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault()
      setOpen(true)
    }
  }

  function onListKeyDown(e: React.KeyboardEvent) {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIndex((i) => Math.min(options.length - 1, i + 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveIndex((i) => Math.max(0, i - 1))
        break
      case 'Home':
        e.preventDefault()
        setActiveIndex(0)
        break
      case 'End':
        e.preventDefault()
        setActiveIndex(options.length - 1)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        commit(activeIndex)
        break
      case 'Escape':
        e.preventDefault()
        setOpen(false)
        triggerRef.current?.focus()
        break
      case 'Tab':
        setOpen(false)
        break
    }
  }

  return (
    <div ref={rootRef} className={`ds-select${className ? ` ${className}` : ''}`} data-open={open}>
      <button
        ref={triggerRef}
        type="button"
        className="ds-select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="ds-select-value">{selected?.label}</span>
        <svg
          className="ds-select-chev"
          width="9"
          height="6"
          viewBox="0 0 9 6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          aria-hidden="true"
        >
          <title>Open</title>
          <path d="M1 1l3.5 3L8 1" />
        </svg>
      </button>
      {open && (
        <ul
          ref={listRef}
          id={listId}
          className="ds-select-menu"
          // biome-ignore lint/a11y/useSemanticElements: WAI-ARIA listbox is the correct pattern for a custom select.
          role="listbox"
          tabIndex={-1}
          aria-label={ariaLabel}
          aria-activedescendant={`${listId}-opt-${activeIndex}`}
          onKeyDown={onListKeyDown}
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-opt-${i}`}
              // biome-ignore lint/a11y/useSemanticElements: option role inside a listbox; keyboard is handled on the container via aria-activedescendant.
              role="option"
              aria-selected={o.value === value}
              className="ds-select-opt"
              data-active={i === activeIndex}
              // biome-ignore lint/a11y/useKeyWithClickEvents: keyboard activation lives on the listbox (aria-activedescendant pattern), not per-option.
              onClick={() => commit(i)}
              onMouseEnter={() => setActiveIndex(i)}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
