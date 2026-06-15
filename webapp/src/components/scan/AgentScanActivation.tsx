import CopyIconButton from '@ui/components/atoms/CopyIconButton'
import Toast from '@ui/components/atoms/Toast'
import Toggle from '@ui/components/atoms/Toggle'
import PromptCodeCard from '@ui/components/molecules/PromptCodeCard'
import TurnstileGate from '@ui/components/molecules/TurnstileGate'
import { useState } from 'react'
import { PRIVATE_NOTE, VIS_EXPLAINER } from '@/components/scan/scan-privacy'
import {
  AGENT_SCAN_TEMPLATE_LINES,
  type MintPlatform,
  type MintSurface,
  type MintVisibility,
  useAgentScanMint,
} from '@/lib/hooks/useAgentScanMint'

// The CLI split `scan` into `capability` + `agent` commands (#90) — the
// behavioral agent scan is `saferskills agent` (cli/README.md).
const CLI_COMMAND = 'npx saferskills agent'

/**
 * Closed platform-picker set — the 8 canonical agents + the platform-agnostic
 * fallback, in the plan's display order. Ids must satisfy the bootstrap
 * endpoint's closed set (it 422s anything else).
 * Mirrors app/agent_scan/bootstrap.py::PLATFORMS
 * (= app/services/agent_compat.py::ALL_AGENTS + "universal").
 * Hint copy verbatim from the agent-scan design's per-platform variants
 * (.local/.brainstorms/done/agent-scan/bootstrap-prompt.md § Per-platform).
 */
export const AGENT_PLATFORMS: ReadonlyArray<{
  id: MintPlatform
  label: string
  hint: string
}> = [
  {
    id: 'claude-code',
    label: 'Claude Code',
    hint: 'Paste into Claude Code (or save as ~/.claude/skills/agent-scan/SKILL.md and run /agent-scan).',
  },
  { id: 'cursor', label: 'Cursor', hint: "Paste into Cursor's chat (Agent mode)." },
  { id: 'codex', label: 'Codex CLI', hint: 'Paste into codex (it can run the curl itself).' },
  { id: 'copilot', label: 'GH Copilot', hint: 'Paste into Copilot Chat (Agent mode).' },
  { id: 'windsurf', label: 'Windsurf', hint: 'Paste into Cascade.' },
  { id: 'cline', label: 'Cline', hint: "Paste into Cline's task box." },
  { id: 'gemini', label: 'Gemini CLI', hint: 'Paste into gemini.' },
  { id: 'openclaw', label: 'OpenClaw', hint: 'Paste into OpenClaw.' },
  { id: 'universal', label: 'Universal', hint: "Paste into your agent's chat." },
]

const UNIVERSAL_PLATFORM = AGENT_PLATFORMS.find((p) => p.id === 'universal') as {
  id: MintPlatform
  label: string
  hint: string
}

const CopyGlyph = () => (
  <svg
    className="cp-ic"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <rect x="8" y="8" width="13" height="13" rx="2" />
    <path d="M5 16V5a2 2 0 0 1 2-2h11" />
  </svg>
)

interface Props {
  /** Telemetry surface — '/scan' agent pane vs the /agents/scan picker page. */
  surface: Extract<MintSurface, 'scan' | 'picker'>
  initialPlatform?: MintPlatform
}

/**
 * The shared agent-scan activation island (I-5.7 plan 03 Module 1) — platform
 * picker → Turnstile-gated mint → the real substituted prompt. Composes plan
 * 02's `PromptCodeCard` + `useAgentScanMint`; consumed by `/scan` (inside
 * `ScanModeShell`, surface='scan') and `/agents/scan` (surface='picker').
 *
 * The picker is a `role="group"` row of toggle buttons (the `.cap-filter`
 * precedent — a selection over one prompt block, NOT tabs over panels, so a
 * tablist would misrepresent the semantics). Pre-mint the card shows the
 * universal TEMPLATE (placeholders visible — never copied); "Generate my scan
 * prompt" mints via the hook (captcha-gated when a site key is configured),
 * copies the substituted prompt, and swaps the foot to the report link
 * (public) or the private-link explainer (unlisted runs 404 on /agents/<id>).
 */
export default function AgentScanActivation({ surface, initialPlatform = 'universal' }: Props) {
  const [platform, setPlatform] = useState<MintPlatform>(initialPlatform)
  const [visibility, setVisibility] = useState<MintVisibility>('public')
  const mint = useAgentScanMint(surface)

  const ready = mint.phase === 'ready' && mint.prompt !== null
  const lines = mint.prompt ? mint.prompt.split('\n') : AGENT_SCAN_TEMPLATE_LINES
  const active = AGENT_PLATFORMS.find((p) => p.id === platform) ?? UNIVERSAL_PLATFORM
  const busy = mint.copyState === 'busy' || mint.phase === 'minting' || mint.phase === 'gating'

  function generate() {
    mint.copy(visibility, platform)
  }

  return (
    <div className={`agent-activation${surface === 'picker' ? ' agent-activation--picker' : ''}`}>
      {/* biome-ignore lint/a11y/useSemanticElements: toggle-button row — role=group is the correct ARIA (the .cap-filter precedent); a fieldset would impose form chrome */}
      <div className="plat-picker" role="group" aria-label="Agent platform">
        {AGENT_PLATFORMS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`pp${platform === p.id ? ' on' : ''}`}
            aria-pressed={platform === p.id}
            // The minted prompt is platform-specific — lock the picker while a
            // prompt is live so the chip/hint can never disagree with what a
            // re-copy puts in the clipboard ("Generate a new prompt" unlocks).
            disabled={ready && p.id !== platform}
            onClick={() => setPlatform(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <p className="plat-hint">{active.hint}</p>

      <PromptCodeCard
        title="SaferSkills Agent Scan Prompt"
        lines={lines}
        tinted
        copyState={mint.copyState}
        onCopy={generate}
        footSlot={
          ready ? (
            mint.mintedVisibility === 'unlisted' ? (
              // Unlisted runs 404 on /agents/<run_id> (token-only access) — no
              // link; the agent prints the private report URL after it submits.
              <span className="pcf-note">
                Prompt ready — your agent prints your <b>private report link</b> when the scan
                completes.
              </span>
            ) : (
              <a className="pcf-link" href={`/agents/${mint.runId}`}>
                Your report will appear at /agents/{mint.runId} <span aria-hidden="true">→</span>
              </a>
            )
          ) : undefined
        }
      />

      <div className="scan-privacy">
        <div className="pv-row">
          <Toggle
            checked={visibility === 'public'}
            onChange={(pub) => setVisibility(pub ? 'public' : 'unlisted')}
            label="Make results public"
            tone="orange"
          />
          <span className="pv-info">
            <button type="button" className="pv-info-btn" aria-label={VIS_EXPLAINER}>
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <circle cx="8" cy="8" r="7" />
                <path d="M8 7.2v4M8 4.6h.01" />
              </svg>
            </button>
            <span className="pv-tip" aria-hidden="true">
              {VIS_EXPLAINER}
            </span>
          </span>
        </div>
        {visibility === 'unlisted' && <p className="pv-note">{PRIVATE_NOTE}</p>}
      </div>

      {ready ? (
        <>
          <button
            type="button"
            className="scan-go copy-prompt"
            data-mode="agent"
            disabled={mint.copyState === 'busy'}
            onClick={generate}
          >
            <CopyGlyph />
            <span className="cp-lbl">Copy &amp; paste into your agent</span>
          </button>
          <button type="button" className="scan-regen" onClick={mint.reset}>
            Generate a new prompt
          </button>
        </>
      ) : (
        <button
          type="button"
          className="scan-go"
          data-mode="agent"
          disabled={busy}
          aria-busy={mint.phase === 'minting'}
          onClick={generate}
        >
          {mint.phase === 'minting' ? (
            'Generating…'
          ) : (
            <>
              Generate my scan prompt{' '}
              <span className="kbd" aria-hidden="true">
                ↵
              </span>
            </>
          )}
        </button>
      )}

      <p className="scan-consent">
        By scanning you confirm you can share this content. Public results are published
        permanently. <a href="/privacy">See Privacy</a>.
      </p>

      <div className="cli-alt">
        <code className="cli-cmd">{CLI_COMMAND}</code>
        <CopyIconButton value={CLI_COMMAND} label="Copy the CLI command" />
        <span className="cli-note">
          Prefer the terminal? Same scan, CI-ready. <a href="/docs">Read the docs</a>
        </span>
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
