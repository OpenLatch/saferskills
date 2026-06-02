// Shared repo-scan (GitHub URL) flow for the dual-mode scan affordance —
// consumed by `ScanConsole` (/scan) and `HomeScanPanel` (homepage + /404). One
// source of truth for the URL field, validation, the bucketed error, and the
// inline submit ceremony. The hosting component owns only the visibility toggle,
// analytics, and navigation (passed in via `submit({ onResult })`). Mirrors
// `useUploadFlow` so both submit paths fire inline from any surface.

import { useState } from 'react'
import { type ScanSubmitResponse, submitScan, type Visibility } from '@/lib/api/scans'
import { uploadErrorMessage } from '@/lib/upload'

// Accept a full github.com URL or a bare `<org>/<repo>` slug (normalized below).
const VALID_URL = /^(https?:\/\/)?(www\.)?github\.com\/[^\s/]+\/[^\s/]+(\/.*)?\/?$/
const VALID_SLUG = /^[^\s/]+\/[^\s/]+$/

export interface RepoScanFlow {
  urlValue: string
  setUrlValue: (v: string) => void
  urlError: string | null
  submitting: boolean
  /** Validate + POST /scans; `onResult` navigates (immediately, or via a fade). */
  submit: (opts: {
    visibility: Visibility
    onResult: (res: ScanSubmitResponse) => void
  }) => Promise<void>
}

export function useRepoScanFlow(): RepoScanFlow {
  const [urlValue, setUrlValue] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit({
    visibility,
    onResult,
  }: {
    visibility: Visibility
    onResult: (res: ScanSubmitResponse) => void
  }): Promise<void> {
    setUrlError(null)
    const raw = urlValue.trim()
    const githubUrl = VALID_SLUG.test(raw) ? `https://github.com/${raw}` : raw
    if (!VALID_URL.test(githubUrl)) {
      setUrlError('Paste a public github.com URL: `github.com/<org>/<repo>`')
      return
    }
    setSubmitting(true)
    try {
      const res = await submitScan({ github_url: githubUrl, visibility })
      // On success we keep `submitting` true through the navigation handoff so
      // the affordance stays disabled until the page changes.
      onResult(res)
    } catch (e) {
      setSubmitting(false)
      if (e instanceof Error && e.message === 'rate_limit_exceeded') {
        setUrlError(uploadErrorMessage('rate_limit_exceeded'))
      } else if (e instanceof Error && e.message === 'invalid_url') {
        setUrlError("The URL didn't resolve to a public GitHub repository.")
      } else {
        setUrlError('Scan submission failed. Try again in a moment.')
      }
    }
  }

  return { urlValue, setUrlValue, urlError, submitting, submit }
}
