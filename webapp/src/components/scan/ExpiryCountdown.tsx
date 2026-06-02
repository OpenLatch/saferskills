import { useEffect, useState } from 'react'

interface Props {
  /** ISO timestamp the unlisted run expires at. */
  expiresAt: string
  /** `pill` → the meta-row "EXPIRES IN N DAYS" pill; `inline` → plain text. */
  variant?: 'pill' | 'inline'
}

/** Human, recomputing remaining-time label from an expiry timestamp.
 *
 * Days while > 48h out, then hours/minutes near the end. Recomputes on an
 * interval (no animated tick — reduced-motion safe by construction; the text
 * just updates). Past expiry shows "Expired" (the API already 404s such a run,
 * so this is a defensive last-frame label). */
function format(expiresAt: string): { label: string; expired: boolean } {
  const ms = new Date(expiresAt).getTime() - Date.now()
  if (Number.isNaN(ms)) return { label: '', expired: false }
  if (ms <= 0) return { label: 'Expired', expired: true }
  const mins = Math.floor(ms / 60000)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (days >= 2) return { label: `Expires in ${days} days`, expired: false }
  if (hours >= 1)
    return { label: `Expires in ${hours} hour${hours === 1 ? '' : 's'}`, expired: false }
  return { label: `Expires in ${Math.max(1, mins)} minute${mins === 1 ? '' : 's'}`, expired: false }
}

export default function ExpiryCountdown({ expiresAt, variant = 'inline' }: Props) {
  const [state, setState] = useState(() => format(expiresAt))

  useEffect(() => {
    setState(format(expiresAt))
    // Recompute once a minute — cheap, and the day/hour rollover stays accurate.
    const t = setInterval(() => setState(format(expiresAt)), 60000)
    return () => clearInterval(t)
  }, [expiresAt])

  if (!state.label) return null
  if (variant === 'pill') {
    return <span className={`expiry-pill${state.expired ? ' expired' : ''}`}>{state.label}</span>
  }
  return <span className={`expiry-text${state.expired ? ' expired' : ''}`}>{state.label}</span>
}
