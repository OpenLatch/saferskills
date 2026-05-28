import { useEffect } from 'react'
import type { RefObject } from 'react'

/**
 * Pure shortcut-matcher. Cmd+K on macOS OR Ctrl+K on Windows/Linux fires.
 * Plain "K" does not. Chord variants (Cmd+Shift+K, Cmd+Alt+K) are filtered
 * so site-wide chords don't collide with platform-specific bindings the
 * user already relies on.
 */
export function isPlatformShortcut(event: KeyboardEvent, key: string): boolean {
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
 * when the platform-specific Cmd/Ctrl+<key> chord fires.
 *
 * Pass `key: ''` to disable — the hook short-circuits without attaching
 * a listener.
 */
export function useFocusShortcut({ key, ref }: Options): void {
  useEffect(() => {
    if (typeof document === 'undefined') return
    if (!key) return
    const handler = (event: KeyboardEvent) => {
      if (!isPlatformShortcut(event, key)) return
      event.preventDefault()
      ref.current?.focus()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [key, ref])
}
