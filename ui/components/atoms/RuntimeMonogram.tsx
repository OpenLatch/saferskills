import { AGENT_LOGOS } from './agent-logos'

/**
 * RuntimeMonogram — a compact agent-runtime badge (brand mark + optional name)
 * for the `/agents` directory (I-5.6 §12). The bordered square carries the
 * agent's real brand logo (the same `AGENT_LOGOS` marks the homepage hero
 * marquee uses); a runtime with no known logo (e.g. `other`) falls back to the
 * 2-letter monogram. The id set mirrors `app/services/agent_compat.py::AgentName`
 * + the telemetry `other` fallback — an unknown runtime falls back to `other`
 * (the enum stays closed). Token-only chip; CSS (`.rt-mono` / `.rt-mark` /
 * `.rt-logo` / `.rt-name`) is in `page-agent-directory.css`.
 */

// Mirrors app/services/agent_compat.py::AgentName + the `other` runtime fallback.
export type RuntimeId =
  | 'claude-code'
  | 'cursor'
  | 'codex'
  | 'copilot'
  | 'windsurf'
  | 'cline'
  | 'gemini'
  | 'openclaw'
  | 'other'

export const RUNTIME_IDS: RuntimeId[] = [
  'claude-code',
  'cursor',
  'codex',
  'copilot',
  'windsurf',
  'cline',
  'gemini',
  'openclaw',
  'other',
]

const MONOGRAM: Record<RuntimeId, string> = {
  'claude-code': 'CC',
  cursor: 'Cu',
  codex: 'Cx',
  copilot: 'Co',
  windsurf: 'Wd',
  cline: 'Cl',
  gemini: 'Gm',
  openclaw: 'OC',
  other: '··',
}

const NAME: Record<RuntimeId, string> = {
  'claude-code': 'Claude Code',
  cursor: 'Cursor',
  codex: 'Codex CLI',
  copilot: 'GH Copilot',
  windsurf: 'Windsurf',
  cline: 'Cline',
  gemini: 'Gemini CLI',
  openclaw: 'OpenClaw',
  other: 'Other',
}

/** Normalize an arbitrary runtime string to a known id (else `other`). */
export function asRuntimeId(runtime: string): RuntimeId {
  return (RUNTIME_IDS as string[]).includes(runtime) ? (runtime as RuntimeId) : 'other'
}

/** Human display name for a runtime id (`other` for an unknown). */
export function runtimeLabel(runtime: string): string {
  return NAME[asRuntimeId(runtime)]
}

export default function RuntimeMonogram({
  runtime,
  showName = false,
  className = '',
}: {
  runtime: string
  /** Render the runtime name next to the monogram. */
  showName?: boolean
  className?: string
}) {
  const id = asRuntimeId(runtime)
  const Logo = AGENT_LOGOS[id]
  return (
    <span className={`rt-mono rt-${id} ${className}`.trim()}>
      <span className={`rt-mark${Logo ? ' rt-mark--logo' : ''}`} aria-hidden="true">
        {Logo ? <Logo className="rt-logo" /> : MONOGRAM[id]}
      </span>
      {showName ? (
        <span className="rt-name">{NAME[id]}</span>
      ) : (
        <span className="sr-only">{NAME[id]}</span>
      )}
    </span>
  )
}
