import type { ScanRunReportDetail } from '@/lib/api/scans'

/** Display identity for a run report — shared by `/scans/[id]`, `/scans/r/[token]`,
 * and `ScanRunReport.astro` so the page `<title>`, the report `<h1>`, and the
 * breadcrumb all derive the same name (null-guarded `github_url`). */
export interface ReportIdentity {
  isUpload: boolean
  /** Best display name: capability name → uploaded filename → generic. */
  uploadName: string
  /** `<org>/<repo>` for GitHub runs, else "". */
  repoName: string
  /** The H1 / page-title base: capability/file name for uploads, repo leaf for GitHub. */
  baseTitle: string
}

/** `aaaa…zzzz` short form of a 64-char sha256 (or `—` when absent). Shared by
 * the page-head meta and the report body so the truncation never desyncs. */
export function shortHash(full: string | null | undefined): string {
  return full ? `${full.slice(0, 4)}…${full.slice(-4)}` : '—'
}

/** `scn_<12 hex>` display id from a run/scan UUID. */
export function scanIdShort(id: string): string {
  return `scn_${id.replace(/-/g, '').slice(0, 12)}`
}

export function reportIdentity(run: ScanRunReportDetail): ReportIdentity {
  const isUpload = run.source_kind === 'upload'
  const uploadName = run.capabilities[0]?.name ?? run.uploaded_filename ?? 'uploaded artifact'
  const repoName = run.github_url
    ? run.github_url
        .replace(/^https?:\/\//, '')
        .replace(/\/$/, '')
        .split('/')
        .slice(1, 3)
        .join('/')
    : ''
  const baseTitle = isUpload ? uploadName : repoName.split('/').pop() || repoName || 'scan'
  return { isUpload, uploadName, repoName, baseTitle }
}
