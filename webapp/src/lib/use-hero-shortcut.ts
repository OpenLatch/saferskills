import type { RefObject } from 'react'
import { useEffect } from 'react'

/**
 * Pure shortcut-matcher. Cmd+K on macOS OR Ctrl+K on Windows/Linux fires.
 * Plain "K" doesn't. We also bail when the user is already inside an
 * editable element (browser default behaviour for Cmd+K varies — playing
 * nice with native form widgets keeps the focus rule predictable).
 */
export function isHeroShortcut(event: KeyboardEvent, key: string): boolean {
  if (!event.metaKey && !event.ctrlKey) return false
  if (event.altKey || event.shiftKey) return false
  return event.key.toLowerCase() === key.toLowerCase()
}

interface Options {
  key: string
  ref: RefObject<HTMLInputElement | null>
}

/**
 * Wire a single `document.keydown` listener that focuses the given input
 * when the platform-specific Cmd/Ctrl+<key> chord fires. Used for the hero
 * Find (⌘K) and Audit (⌘J) shortcuts.
 */
export function useHeroShortcut({ key, ref }: Options): void {
  useEffect(() => {
    if (typeof document === 'undefined') return
    if (!key) return
    const handler = (event: KeyboardEvent) => {
      if (!isHeroShortcut(event, key)) return
      event.preventDefault()
      ref.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [key, ref])
}
