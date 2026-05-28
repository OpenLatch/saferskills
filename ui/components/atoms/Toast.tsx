import { useEffect, useState } from 'react'

let externalShow: ((msg: string, ms?: number) => void) | null = null

/**
 * Imperative global toast — `flashToast(msg)` shows it bottom-center for
 * ~1.7s. Used by CopyButton + future install-success notifications.
 */
export function flashToast(message: string, durationMs = 1700): void {
  externalShow?.(message, durationMs)
}

/**
 * Single Toast root — mount once near the page bottom (in Base.astro layout
 * or any page that needs imperative toasts).
 */
export default function Toast() {
  const [state, setState] = useState<{ message: string; visible: boolean }>({
    message: '',
    visible: false,
  })

  useEffect(() => {
    externalShow = (msg: string, ms: number = 1700) => {
      setState({ message: msg, visible: true })
      setTimeout(() => setState((s) => ({ ...s, visible: false })), ms)
    }
    return () => { externalShow = null }
  }, [])

  return (
    <div
      className={`toast ${state.visible ? 'show' : ''}`.trim()}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      {state.message}
    </div>
  )
}
