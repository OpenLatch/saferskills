import { type CSSProperties, type DragEvent, useState } from 'react'

export type DropZoneState = 'idle' | 'dragover' | 'selected' | 'uploading' | 'error'

export interface SelectedFile {
  name: string
  size: number
  kind?: string
}

interface DropZoneProps {
  /** Report the newly-picked files. Append semantics live in the parent. */
  onFilesSelected: (files: File[]) => void
  /** Extension allowlist — drives the picker `accept` + the subtext copy. */
  accept: string[]
  /** Client pre-check ceiling (server is authoritative) — drives the subtext copy. */
  maxBytes: number
  /** Optional descriptive subtext (after "Single file or .zip · max N MiB · ").
   *  Defaults to the raw extension list — callers pass domain copy. */
  hint?: string
  /** Controlled machine state (parent owns idle/selected/uploading/error). */
  state?: DropZoneState
  /** 0..1 for the `uploading` determinate bar + aggregate byte counter. */
  progress?: number
  /** The accumulated files (the parent owns the list; DropZone renders it). */
  selectedFiles?: SelectedFile[]
  error?: { code: string; message: string }
  /** Remove the file at `index` from the parent's list. */
  onRemove?: (index: number) => void
  /** Compact row layout (homepage audit panel). */
  compact?: boolean
}

const MIB = 1024 * 1024
const KIB = 1024

function humanBytes(n: number): string {
  if (n >= MIB) return `${(n / MIB).toFixed(n % MIB === 0 ? 0 : 1)} MiB`
  if (n >= KIB) return `${(n / KIB).toFixed(1)} KiB`
  return `${n} B`
}

/**
 * Drag-and-drop + click-to-browse upload affordance — the animated D-UP-ANIM
 * state machine (CSS in `ui/styles/components.css` under `.dropzone--*`). Fully
 * controlled: the parent owns `state`/`selectedFiles`/`progress`/`error`; this
 * component overlays a transient `dragover` look while a drag is in flight.
 */
export default function DropZone({
  onFilesSelected,
  accept,
  maxBytes,
  hint,
  state = 'idle',
  progress = 0,
  selectedFiles,
  error,
  onRemove,
  compact,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false)

  const effState: DropZoneState = dragging && state === 'idle' ? 'dragover' : state
  const files = selectedFiles ?? []
  const uploading = state === 'uploading'

  function pick(picked: FileList | null) {
    if (!picked || picked.length === 0) return
    onFilesSelected(Array.from(picked))
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files)
  }
  function onDragOver(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
  }
  function onDragEnter(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setDragging(true)
  }
  function onDragLeave(e: DragEvent<HTMLLabelElement>) {
    // Only clear when the pointer leaves the zone itself, not a child.
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    setDragging(false)
  }

  const totalBytes = files.reduce((sum, f) => sum + f.size, 0)
  const fileCount = files.length

  const liveMsg =
    effState === 'error' && error
      ? `Upload error: ${error.message}`
      : uploading
        ? `Uploading ${fileCount} file${fileCount === 1 ? '' : 's'}, ${Math.round(progress * 100)} percent`
        : fileCount > 0
          ? `${fileCount} file${fileCount === 1 ? '' : 's'} selected`
          : ''

  return (
    <div className={`dropzone${compact ? ' dropzone--compact' : ''}`} data-state={effState}>
      {/* A <label> wraps the real file input: native click-to-open + a
          keyboard-focusable control, with no nested-interactive violation.
          The zone stays a drop/click target while files are selected (add more). */}
      <label
        className="dz-zone"
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
      >
        <input
          type="file"
          multiple
          accept={accept.join(',')}
          aria-label="Upload files — drag and drop or browse"
          className="sr-only"
          onChange={(e) => {
            pick(e.target.files)
            e.target.value = ''
          }}
        />
        <span className="dz-glyph" aria-hidden="true">
          <UploadGlyph />
        </span>
        <p className="dz-main">
          Drag a file or .zip here, or <span className="dz-browse">click to browse</span>
        </p>
        {/* The sub-line collapses (grid-rows 1fr→0fr) once files are picked,
            shrinking the zone to glyph + sentence — see components.css. */}
        <p className="dz-sub">
          <span>
            One file, a .zip, or several files · max {humanBytes(maxBytes)} ·{' '}
            {hint ?? accept.join(' ')}
          </span>
        </p>
      </label>

      {fileCount > 0 && (
        <ul className="dz-files" aria-label="Selected files">
          {files.map((f, i) => (
            <li
              className="dz-file"
              key={`${f.name}-${i}`}
              style={{ '--dz-i': i } as CSSProperties}
            >
              <span className="ff-ic" aria-hidden="true">
                <FileGlyph />
              </span>
              <span className="ff-name">{f.name}</span>
              <span className="ff-size">{humanBytes(f.size)}</span>
              {!uploading && (
                <>
                  {f.kind && <span className="ff-kind">{f.kind}</span>}
                  {onRemove && (
                    <button
                      type="button"
                      className="ff-x"
                      aria-label={`Remove ${f.name}`}
                      onClick={() => onRemove(i)}
                    >
                      ×
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {uploading && fileCount > 0 && (
        <div className="dz-upload">
          <span className="dz-sweep" aria-hidden="true" />
          <span className="dz-bytes">
            {humanBytes(Math.min(totalBytes, Math.round(progress * totalBytes)))} /{' '}
            {humanBytes(totalBytes)}
          </span>
          <span className="dz-progress" aria-hidden="true">
            <i style={{ '--dz-frac': Math.max(0, Math.min(1, progress)) } as CSSProperties} />
          </span>
        </div>
      )}

      {effState === 'error' && error && <p className="dz-error">{error.message}</p>}

      <span className="sr-only" aria-live="polite">
        {liveMsg}
      </span>
    </div>
  )
}

const UploadGlyph = () => (
  <svg
    width="22"
    height="22"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="square"
    strokeLinejoin="miter"
    aria-hidden="true"
  >
    <path d="M12 15V3" />
    <path d="m7 8 5-5 5 5" />
    <path d="M3 15v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4" />
  </svg>
)

const FileGlyph = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="square"
    strokeLinejoin="miter"
    aria-hidden="true"
  >
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
    <path d="M14 3v6h6" />
  </svg>
)
