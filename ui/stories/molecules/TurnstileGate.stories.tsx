import type { Story } from '@ladle/react'
import { useState } from 'react'
import TurnstileGate from '../../components/molecules/TurnstileGate'

// Cloudflare's always-pass TEST site key — safe to commit, exercises the real
// widget without a real account. (Secret side uses 1x000...AA in non-prod.)
const TEST_SITE_KEY = '1x00000000000000000000AA'

/** Toggle the gate open; on verify we just show the token (host would submit). */
export const Default: Story = () => {
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 420 }}>
      <button type="button" className="btn primary sm" onClick={() => setOpen(true)}>
        Scan now
      </button>
      {token && <code style={{ fontSize: 12 }}>verified token: {token.slice(0, 16)}…</code>}
      <TurnstileGate
        open={open}
        siteKey={TEST_SITE_KEY}
        onVerified={(t) => {
          setToken(t)
          setOpen(false)
        }}
        onCancel={() => setOpen(false)}
      />
    </div>
  )
}

/** Opens immediately — the resting modal state for visual review. */
export const Open: Story = () => (
  <TurnstileGate open siteKey={TEST_SITE_KEY} onVerified={() => {}} onCancel={() => {}} />
)
