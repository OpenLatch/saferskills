/**
 * RuntimeMonogram — a compact agent-runtime badge (monogram + optional name) for
 * the `/agents` directory (I-5.6 §12). The id set mirrors
 * `app/services/agent_compat.py::AgentName` + the telemetry `other` fallback — an
 * unknown runtime falls back to `other` (the enum stays closed). Token-only chip;
 * CSS (`.rt-mono` / `.rt-mark` / `.rt-name`) is in `page-agent-directory.css`.
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
  windsurf: 'Ws',
  cline: 'Cl',
  gemini: 'Ge',
  openclaw: 'Oc',
  other: '··',
}

const NAME: Record<RuntimeId, string> = {
  'claude-code': 'Claude Code',
  cursor: 'Cursor',
  codex: 'Codex',
  copilot: 'Copilot',
  windsurf: 'Windsurf',
  cline: 'Cline',
  gemini: 'Gemini',
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
  return (
    <span className={`rt-mono rt-${id} ${className}`.trim()}>
      <span className="rt-mark" aria-hidden="true">
        {MONOGRAM[id]}
      </span>
      {showName ? (
        <span className="rt-name">{NAME[id]}</span>
      ) : (
        <span className="sr-only">{NAME[id]}</span>
      )}
    </span>
  )
}
