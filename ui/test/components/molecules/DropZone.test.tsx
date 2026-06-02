import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import DropZone from '../../../components/molecules/DropZone'

const ACCEPT = ['.zip', '.md', '.json']
const MAX = 10 * 1024 * 1024

function makeFile(name = 'SKILL.md') {
  return new File(['# skill'], name, { type: 'text/markdown' })
}

const FILES = [
  { name: 'SKILL.md', size: 3277, kind: 'Skill' },
  { name: 'extract.py', size: 1024, kind: 'Script' },
]

describe('DropZone', () => {
  it('renders the idle prompt with allowed-type + size subtext', () => {
    render(<DropZone onFilesSelected={() => {}} accept={ACCEPT} maxBytes={MAX} state="idle" />)
    expect(screen.getByText(/click to browse/i)).toBeInTheDocument()
    expect(screen.getByText(/max 10 MiB/i)).toBeInTheDocument()
  })

  it('emits onFilesSelected from the file input (multiple)', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(
      <DropZone onFilesSelected={onFilesSelected} accept={ACCEPT} maxBytes={MAX} state="idle" />,
    )
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(true)
    fireEvent.change(input, { target: { files: [makeFile('a.md'), makeFile('b.md')] } })
    expect(onFilesSelected).toHaveBeenCalledTimes(1)
    expect(onFilesSelected.mock.calls[0][0].map((f: File) => f.name)).toEqual(['a.md', 'b.md'])
  })

  it('emits onFilesSelected on drop with all dropped files', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(
      <DropZone onFilesSelected={onFilesSelected} accept={ACCEPT} maxBytes={MAX} state="idle" />,
    )
    const zone = container.querySelector('.dz-zone') as HTMLElement
    fireEvent.dragEnter(zone)
    fireEvent.drop(zone, { dataTransfer: { files: [makeFile('mcp.json'), makeFile('run.py')] } })
    expect(onFilesSelected).toHaveBeenCalledTimes(1)
    expect(onFilesSelected.mock.calls[0][0].map((f: File) => f.name)).toEqual(['mcp.json', 'run.py'])
  })

  it('renders a list of selected-file cards with remove by index', () => {
    const onRemove = vi.fn()
    render(
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="selected"
        selectedFiles={FILES}
        onRemove={onRemove}
      />,
    )
    expect(screen.getByText('SKILL.md')).toBeInTheDocument()
    expect(screen.getByText('extract.py')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /remove extract\.py/i }))
    expect(onRemove).toHaveBeenCalledWith(1)
  })

  it('shows an aggregate byte counter while uploading', () => {
    render(
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="uploading"
        selectedFiles={FILES}
        progress={0.5}
      />,
    )
    // 3277 + 1024 = 4301 bytes ≈ 4.2 KiB total.
    expect(screen.getByText(/\/ 4\.2 KiB/)).toBeInTheDocument()
  })

  it('renders the bucketed error message', () => {
    render(
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="error"
        error={{ code: 'upload_too_large', message: 'File is larger than the 10 MiB limit.' }}
      />,
    )
    expect(
      screen.getByText(/larger than the 10 MiB limit/i, { selector: '.dz-error' }),
    ).toBeInTheDocument()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <DropZone
        onFilesSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="selected"
        selectedFiles={FILES}
        onRemove={() => {}}
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
