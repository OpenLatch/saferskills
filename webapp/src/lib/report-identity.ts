import type { ScanRunReportDetail } from '@/lib/api/scans'

/** Display identity for a run report — shared by `/scans/[id]`, `/scans/r/[token]`,
 * and `ScanRunReport.astro` so the page `<title>`, the report `<h1>`, and the
 * breadcrumb all derive the same name (P0-9: null-guarded `github_url`). */
export interface ReportIdentity {
  isUpload: boolean
  /** Best display name: capability name → uploaded filename → generic. */
  uploadName: string
  /** `<org>/<repo>` for GitHub runs, else "". */
  repoName: string
  /** The H1 / page-title base: capability/file name for uploads, repo leaf for GitHub. */
  baseTitle: string
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
