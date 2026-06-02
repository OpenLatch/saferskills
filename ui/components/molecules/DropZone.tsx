import { type CSSProperties, type DragEvent, useState } from 'react'

export type DropZoneState = 'idle' | 'dragover' | 'selected' | 'uploading' | 'error'

interface DropZoneProps {
  onFileSelected: (file: File) => void
  /** Extension allowlist — drives the picker `accept` + the subtext copy. */
  accept: string[]
  /** Client pre-check ceiling (server is authoritative) — drives the subtext copy. */
  maxBytes: number
  /** Optional descriptive subtext (after "Single file or .zip · max N MiB · ").
   *  Defaults to the raw extension list — callers pass domain copy. */
  hint?: string
  /** Controlled machine state (parent owns idle/selected/uploading/error). */
  state?: DropZoneState
  /** 0..1 for the `uploading` determinate bar + byte counter. */
  progress?: number
  selectedFile?: { name: string; size: number; kind?: string }
  error?: { code: string; message: string }
  onRemove?: () => void
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
 * controlled: the parent owns `state`/`selectedFile`/`progress`/`error`; this
 * component overlays a transient `dragover` look while a drag is in flight.
 */
export default function DropZone({
  onFileSelected,
  accept,
  maxBytes,
  hint,
  state = 'idle',
  progress = 0,
  selectedFile,
  error,
  onRemove,
  compact,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false)

  const effState: DropZoneState = dragging && state === 'idle' ? 'dragover' : state

  function pick(file: File | undefined) {
    if (file) onFileSelected(file)
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files?.[0])
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

  const liveMsg =
    effState === 'error' && error
      ? `Upload error: ${error.message}`
      : state === 'uploading'
        ? `Uploading ${selectedFile?.name ?? 'file'}, ${Math.round(progress * 100)} percent`
        : selectedFile
          ? `Selected ${selectedFile.name}${selectedFile.kind ? `, detected ${selectedFile.kind}` : ''}`
          : ''

  return (
    <div className={`dropzone${compact ? ' dropzone--compact' : ''}`} data-state={effState}>
      {/* A <label> wraps the real file input: native click-to-open + a
          keyboard-focusable control, with no nested-interactive violation. */}
      <label
        className="dz-zone"
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
      >
        <input
          type="file"
          accept={accept.join(',')}
          aria-label="Upload a file — drag and drop or browse"
          className="sr-only"
          onChange={(e) => {
            pick(e.target.files?.[0])
            e.target.value = ''
          }}
        />
        <span className="dz-glyph" aria-hidden="true">
          <UploadGlyph />
        </span>
        <p className="dz-main">
          Drag a file or .zip here, or <span className="dz-browse">click to browse</span>
        </p>
        <p className="dz-sub">
          Single file or .zip · max {humanBytes(maxBytes)} · {hint ?? accept.join(' ')}
        </p>
      </label>

      {selectedFile && (
        <div className="dz-file">
          {state === 'uploading' && <span className="dz-sweep" aria-hidden="true" />}
          <span className="ff-ic" aria-hidden="true">
            <FileGlyph />
          </span>
          <span className="ff-name">{selectedFile.name}</span>
          <span className="ff-size">{humanBytes(selectedFile.size)}</span>
          {state === 'uploading' ? (
            <span className="dz-bytes">
              {humanBytes(Math.min(selectedFile.size, Math.round(progress * selectedFile.size)))} /{' '}
              {humanBytes(selectedFile.size)}
            </span>
          ) : (
            <>
              {selectedFile.kind && <span className="ff-kind">{selectedFile.kind}</span>}
              {onRemove && (
                <button type="button" className="ff-x" aria-label="Remove file" onClick={onRemove}>
                  ×
                </button>
              )}
            </>
          )}
          {state === 'uploading' && (
            <span className="dz-progress" aria-hidden="true">
              <i style={{ '--dz-frac': Math.max(0, Math.min(1, progress)) } as CSSProperties} />
            </span>
          )}
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
