// Shared Cloudflare Turnstile gate state for the dual-mode scan affordance —
// consumed by `ScanConsole` (/scan) and `HomeScanPanel` (homepage + /404), the
// same way both share `useUploadFlow` / `useRepoScanFlow`. Owns the modal
// open/close + the pending scan-mode; the host owns the actual submit dispatch
// (which differs: immediate navigate vs faded handoff). When no site key is
// configured the gate is inert and `request()` tells the host to submit directly.

import { useState } from 'react'
import { env } from '@/env'

export type ScanMode = 'upload' | 'url'

export interface CaptchaGate {
  /** The configured site key, or undefined → gate disabled (dev). */
  siteKey: string | undefined
  /** Whether the modal is currently open. */
  gateOpen: boolean
  /** Open the gate for `mode` and return `true` (host waits for `onVerified`);
   *  or return `false` when no key is configured (host submits directly). */
  request: (mode: ScanMode) => boolean
  /** Close the gate on a verified token; returns the pending mode to dispatch. */
  resolve: () => ScanMode | null
  /** Re-open a fresh gate for `mode` after a consumed-token `403 captcha_failed`. */
  reopen: (mode: ScanMode) => void
  /** Escape / backdrop / Cancel — close + clear the pending mode. */
  cancel: () => void
}

export function useCaptchaGate(): CaptchaGate {
  const siteKey = env.PUBLIC_TURNSTILE_SITE_KEY
  const [gateOpen, setGateOpen] = useState(false)
  const [pending, setPending] = useState<ScanMode | null>(null)

  function reopen(mode: ScanMode): void {
    setPending(mode)
    setGateOpen(true)
  }

  function request(mode: ScanMode): boolean {
    if (!siteKey) return false
    reopen(mode)
    return true
  }

  function resolve(): ScanMode | null {
    setGateOpen(false)
    setPending(null)
    return pending
  }

  function cancel(): void {
    setGateOpen(false)
    setPending(null)
  }

  return { siteKey, gateOpen, request, resolve, reopen, cancel }
}
