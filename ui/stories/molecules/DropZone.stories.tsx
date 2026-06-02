import type { Story } from '@ladle/react'
import { useEffect, useRef, useState } from 'react'
import DropZone, { type DropZoneState } from '../../components/molecules/DropZone'

const ACCEPT = ['.zip', '.md', '.json', '.yaml', '.yml', '.toml', '.txt', '.js', '.ts', '.py', '.sh']
const MAX = 10 * 1024 * 1024
const FILE = { name: 'SKILL.md', size: 3277, kind: 'Skill' }
const FILES = [
  { name: 'SKILL.md', size: 3277, kind: 'Skill' },
  { name: 'extract.py', size: 1840, kind: 'Script' },
  { name: 'config.json', size: 512, kind: 'Config' },
]

export const Idle: Story = () => (
  <div style={{ maxWidth: 520 }}>
    <DropZone onFilesSelected={() => {}} accept={ACCEPT} maxBytes={MAX} state="idle" />
  </div>
)

export const Selected: Story = () => (
  <div style={{ maxWidth: 520 }}>
    <DropZone
      onFilesSelected={() => {}}
      accept={ACCEPT}
      maxBytes={MAX}
      state="selected"
      selectedFiles={[FILE]}
      onRemove={() => {}}
    />
  </div>
)

export const MultiSelected: Story = () => (
  <div style={{ maxWidth: 520 }}>
    <DropZone
      onFilesSelected={() => {}}
      accept={ACCEPT}
      maxBytes={MAX}
      state="selected"
      selectedFiles={FILES}
      onRemove={() => {}}
    />
  </div>
)

export const Uploading: Story = () => {
  const [p, setP] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setP((x) => (x >= 1 ? 0 : x + 0.04)), 120)
    return () => clearInterval(t)
  }, [])
  return (
    <div style={{ maxWidth: 520 }}>
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="uploading"
        selectedFiles={FILES}
        progress={p}
      />
    </div>
  )
}

export const ErrorState: Story = () => (
  <div style={{ maxWidth: 520 }}>
    <DropZone
      onFilesSelected={() => {}}
      accept={ACCEPT}
      maxBytes={MAX}
      state="error"
      error={{ code: 'upload_too_large', message: 'File is larger than the 10 MiB limit.' }}
    />
  </div>
)

export const Compact: Story = () => (
  <div style={{ maxWidth: 360 }}>
    <DropZone onFilesSelected={() => {}} accept={['.zip', '.md']} maxBytes={MAX} state="idle" compact />
  </div>
)

/** Step through the whole machine — the visual gate records motion from this. */
export const StateMachine: Story = () => {
  const [state, setState] = useState<DropZoneState>('idle')
  const [progress, setProgress] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval>>(undefined)

  useEffect(() => {
    clearInterval(timer.current)
    if (state === 'uploading') {
      setProgress(0)
      timer.current = setInterval(() => setProgress((x) => (x >= 1 ? 1 : x + 0.05)), 120)
    }
    return () => clearInterval(timer.current)
  }, [state])

  const states: DropZoneState[] = ['idle', 'dragover', 'selected', 'uploading', 'error']
  return (
    <div style={{ maxWidth: 520, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {states.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setState(s)}
            style={{ font: '11px monospace', padding: '4px 10px', border: '1px solid #CBD5E1' }}
          >
            {s}
          </button>
        ))}
      </div>
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state={state}
        progress={progress}
        selectedFiles={state === 'selected' || state === 'uploading' ? FILES : undefined}
        error={state === 'error' ? { code: 'archive_rejected', message: 'Archive rejected: ratio cap exceeded.' } : undefined}
        onRemove={() => setState('idle')}
      />
    </div>
  )
}
