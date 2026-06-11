import Toast from '@ui/components/atoms/Toast'
import Toggle from '@ui/components/atoms/Toggle'
import PromptCodeCard from '@ui/components/molecules/PromptCodeCard'
import TurnstileGate from '@ui/components/molecules/TurnstileGate'
import { useState } from 'react'
import {
  AGENT_SCAN_TEMPLATE_LINES,
  type MintVisibility,
  useAgentScanMint,
} from '@/lib/hooks/useAgentScanMint'

/**
 * Homepage hero card 02 — "Scan a Running Agent" (I-5.7 D-5.7-03, the inline
 * mint card). Pre-mint the PromptCodeCard shows the canonical TEMPLATE block
 * (the `{{…}}` placeholders make it clearly a preview); Copy = mint: the hook
 * Turnstile-gates, POSTs /api/v1/agent-scans/bootstrap, copies the REAL
 * substituted prompt, and the card foot swaps to the /agents/<run_id> report
 * link. The visibility toggle feeds the mint.
 *
 * The island renders the full `.p1-card.assess` (head + body + foot) so the
 * foot swap lives inside one React tree; `<astro-island>` is display:contents,
 * so the card stays a direct grid child of `.hero-cards.vb-grid`.
 */

export default function AgentScanHeroCard() {
  const [visibility, setVisibility] = useState<MintVisibility>('public')
  const mint = useAgentScanMint('homepage')

  // Post-mint the body shows the real prompt (what is actually in the
  // clipboard); pre-mint it shows the template preview.
  const lines = mint.prompt ? mint.prompt.split('\n') : AGENT_SCAN_TEMPLATE_LINES

  return (
    <div className="p1-card assess">
      <div className="p1-head">
        <span className="seq">02</span>
        <span className="hd-title">Scan a Running Agent</span>
        <span className="pulse">Live</span>
      </div>
      <div className="p1-body">
        <div>
          <p className="p1-blurb">
            Drop this prompt into your agent — it self-scans and posts the evidence back.
          </p>
        </div>
        <PromptCodeCard
          title="SaferSkills Agent Scan Prompt"
          lines={lines}
          copyState={mint.copyState}
          onCopy={() => mint.copy(visibility)}
        />
        <div className="scan-vis">
          <Toggle
            compact
            checked={visibility === 'public'}
            onChange={(pub) => setVisibility(pub ? 'public' : 'unlisted')}
            label="Make results public"
          />
        </div>
      </div>
      <div className="p1-foot">
        {mint.phase === 'ready' && mint.runId ? (
          mint.mintedVisibility === 'unlisted' ? (
            // Unlisted runs 404 on /agents/<run_id> (token-only access) — no
            // link; the agent prints the private report URL after it submits.
            <span className="meta">
              Prompt ready — your agent prints your <b>private report link</b> when the scan
              completes.
            </span>
          ) : (
            <a className="p1-cta" href={`/agents/${mint.runId}`}>
              Prompt copied — your report will appear at /agents/{mint.runId}{' '}
              <span className="p1-cta-arrow" aria-hidden="true">
                →
              </span>
            </a>
          )
        ) : (
          <>
            <a className="p1-cta" href="/scan?mode=agent">
              Scan an agent{' '}
              <span className="p1-cta-arrow" aria-hidden="true">
                →
              </span>
            </a>
            <span className="meta">
              avg <b>5min</b> · free
            </span>
          </>
        )}
      </div>
      {mint.siteKey && (
        <TurnstileGate
          open={mint.phase === 'gating'}
          siteKey={mint.siteKey}
          onVerified={mint.onGateVerified}
          onCancel={mint.onGateCancel}
        />
      )}
      {/* flashToast is per-island — the mint error toasts need an in-tree root. */}
      <Toast />
    </div>
  )
}
