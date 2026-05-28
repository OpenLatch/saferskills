import { useEffect, useState } from 'react'

/**
 * Pure platform detection — accepts the navigator string so the test can
 * exercise both branches without monkey-patching globals. SSR-safe at the
 * call site via the hook's two-pass render.
 */
export function detectIsMac(platform: string | undefined): boolean {
  if (!platform) return false
  return platform.toLowerCase().startsWith('mac')
}

/**
 * Render the platform-appropriate shortcut label.
 *   formatShortcut('K', true)  → '⌘K'
 *   formatShortcut('K', false) → 'Ctrl+K'
 */
export function formatShortcut(key: string, isMac: boolean): string {
  const upper = key.toUpperCase()
  return isMac ? `⌘${upper}` : `Ctrl+${upper}`
}

/**
 * SSR-safe Mac detection. Returns `false` on first render (so SSR and
 * hydration agree on the Windows label), then flips to the real platform
 * after mount.
 */
export function useIsMac(): boolean {
  const [isMac, setIsMac] = useState(false)
  useEffect(() => {
    if (typeof navigator === 'undefined') return
    setIsMac(detectIsMac(navigator.platform))
  }, [])
  return isMac
}
