// Client-side upload helpers shared by the /scan ScanConsole and the homepage
// audit panel. The server is authoritative — this is UX-only pre-validation +
// the bucketed-error copy that the DropZone renders. Mirrors the backend
// allowlist/caps (app/scan/upload.py + config) so the client rejects early.

export const UPLOAD_ACCEPT = [
  '.zip',
  '.md',
  '.json',
  '.yaml',
  '.yml',
  '.toml',
  '.txt',
  '.js',
  '.ts',
  '.py',
  '.sh',
] as const

export const UPLOAD_MAX_BYTES = 10 * 1024 * 1024 // 10 MiB — matches UPLOAD_MAX_BYTES

/** DropZone subtext descriptor (after "Single file or .zip · max 10 MiB · "). */
export const UPLOAD_HINT =
  'SKILL.md, MCP manifest, hooks, plugin, rules (.zip .md .json .yaml .toml .txt .js .ts .py .sh)'

/** The dual-mode scan tabs — shared by /scan (ScanConsole) + the homepage panel. */
export const SCAN_TABS = [
  { id: 'upload', label: 'Upload', accent: 'teal' as const },
  { id: 'url', label: 'Scan repo', accent: 'orange' as const },
]

export type PrecheckResult = { ok: true } | { ok: false; code: string; message: string }

/** Extension + size pre-check (UX only; the server re-validates authoritatively). */
export function precheckFile(file: File): PrecheckResult {
  const lower = file.name.toLowerCase()
  if (!UPLOAD_ACCEPT.some((ext) => lower.endsWith(ext))) {
    return { ok: false, code: 'unsupported_type', message: uploadErrorMessage('unsupported_type') }
  }
  if (file.size > UPLOAD_MAX_BYTES) {
    return { ok: false, code: 'upload_too_large', message: uploadErrorMessage('upload_too_large') }
  }
  return { ok: true }
}

/** Cosmetic detected-kind chip guess — the backend auto-detection is authoritative. */
export function guessKind(file: File): string | undefined {
  const n = file.name.toLowerCase()
  if (n.endsWith('.zip')) return 'Archive'
  if (n.includes('skill') || n.endsWith('.md')) return 'Skill'
  if (n.includes('mcp')) return 'MCP'
  if (n.includes('plugin')) return 'Plugin'
  if (n.includes('hook')) return 'Hooks'
  return undefined
}

const ARCHIVE_REASONS: Record<string, string> = {
  too_big: 'Archive is too large once expanded.',
  ratio: 'Archive expands too much — blocked by the zip-bomb guard.',
  entries: 'Archive has too many files.',
  nesting: 'Nested archives aren’t allowed.',
  zip_slip: 'Archive contains an unsafe path.',
  bad_path: 'Archive contains an unsafe path.',
  dup_path: 'Archive has duplicate paths.',
}

/** Bucketed, human copy for an upload rejection (code from the API + optional reason). */
export function uploadErrorMessage(code: string, reason?: string): string {
  switch (code) {
    case 'upload_too_large':
      return 'File is larger than the 10 MiB limit.'
    case 'unsupported_type':
      return 'That file type isn’t supported. Allowed: a single text file or a .zip.'
    case 'binary_not_allowed':
      return 'That looks like a binary file — upload a text file or a .zip.'
    case 'archive_rejected':
      return (reason && ARCHIVE_REASONS[reason]) || 'Archive rejected by the safety checks.'
    case 'rate_limit_exceeded':
      return '10 scans/day per IP. Try again tomorrow or pin a previous scan.'
    case 'no_file':
      return 'Choose a file to scan.'
    default:
      return 'Upload failed. Try again in a moment.'
  }
}
