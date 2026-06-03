// Shared upload-flow state for the dual-mode scan affordance — consumed by
// `ScanConsole` (/scan) and `HomeScanPanel` (homepage + /404). One source of
// truth for the accumulated `File[]`, the DropZone machine state, aggregate
// progress, and the bucketed error, plus the inline `submit` ceremony. The
// hosting component owns only the visibility toggle, the URL tab, analytics,
// and navigation (passed in via `submit({ onResult })`).

import type { DropZoneState, SelectedFile } from '@ui/components/molecules/DropZone'
import { useState } from 'react'
import {
  type ScanUploadResponse,
  submitUpload,
  UploadError,
  type Visibility,
} from '@/lib/api/scans'
import { guessKind, precheckFile, uploadErrorMessage } from '@/lib/upload'

export interface DzError {
  code: string
  message: string
}

export interface UploadFlow {
  files: File[]
  /** DropZone-ready descriptors (name/size + cosmetic kind guess). */
  selectedFiles: SelectedFile[]
  dzState: DropZoneState
  progress: number
  dzError: DzError | null
  /** True while the inline upload is in flight (disable submit affordances). */
  uploading: boolean
  /** Precheck each picked file; append the valid ones, surface the first reject. */
  onFiles: (incoming: File[]) => void
  /** Remove the file at `index`; resets to idle when the list empties. */
  onRemove: (index: number) => void
  /** Run the inline upload of the accumulated files; `onResult` navigates. */
  submit: (opts: {
    visibility: Visibility
    /** Verified Turnstile token (omitted when the gate is unconfigured). */
    captchaToken?: string
    onResult: (res: ScanUploadResponse) => void
    /** Called on a `403 captcha_failed` so the host re-opens a fresh gate
     *  (the single-use token was already consumed). */
    onCaptchaRetry?: () => void
  }) => Promise<void>
}

export function useUploadFlow(): UploadFlow {
  const [files, setFiles] = useState<File[]>([])
  const [dzState, setDzState] = useState<DropZoneState>('idle')
  const [progress, setProgress] = useState(0)
  const [dzError, setDzError] = useState<DzError | null>(null)

  function onFiles(incoming: File[]): void {
    const valid: File[] = []
    let rejection: DzError | null = null
    for (const f of incoming) {
      const pre = precheckFile(f)
      if (pre.ok) valid.push(f)
      else if (!rejection) rejection = { code: pre.code, message: pre.message }
    }
    if (valid.length > 0) setFiles((prev) => [...prev, ...valid])
    // A reject takes the machine to `error` (even if some valid files appended,
    // so the list grows AND the bucketed message shows); otherwise `selected`.
    if (rejection) {
      setDzError(rejection)
      setDzState('error')
    } else {
      setDzError(null)
      setDzState('selected')
    }
  }

  function onRemove(index: number): void {
    const next = files.filter((_, i) => i !== index)
    setFiles(next)
    setDzError(null)
    setDzState(next.length === 0 ? 'idle' : 'selected')
  }

  async function submit({
    visibility,
    captchaToken,
    onResult,
    onCaptchaRetry,
  }: {
    visibility: Visibility
    captchaToken?: string
    onResult: (res: ScanUploadResponse) => void
    onCaptchaRetry?: () => void
  }): Promise<void> {
    if (files.length === 0) {
      setDzError({ code: 'no_file', message: uploadErrorMessage('no_file') })
      setDzState('error')
      return
    }
    setDzError(null)
    setProgress(0)
    setDzState('uploading')
    try {
      const res = await submitUpload(files, { visibility, captchaToken }, (loaded, total) =>
        setProgress(total ? loaded / total : 0)
      )
      setProgress(1)
      onResult(res)
    } catch (e) {
      // The single-use token was consumed; bounce back to `selected` (no scary
      // error) and let the host re-open a fresh gate for another attempt.
      if (e instanceof UploadError && e.code === 'captcha_failed' && onCaptchaRetry) {
        setDzError(null)
        setDzState('selected')
        onCaptchaRetry()
        return
      }
      if (e instanceof UploadError) {
        setDzError({ code: e.code, message: uploadErrorMessage(e.code, e.reason) })
      } else {
        setDzError({ code: 'upload_failed', message: uploadErrorMessage('upload_failed') })
      }
      setDzState('error')
    }
  }

  return {
    files,
    selectedFiles: files.map((f) => ({ name: f.name, size: f.size, kind: guessKind(f) })),
    dzState,
    progress,
    dzError,
    uploading: dzState === 'uploading',
    onFiles,
    onRemove,
    submit,
  }
}
