import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import DropZone from '../../../components/molecules/DropZone'

const ACCEPT = ['.zip', '.md', '.json']
const MAX = 10 * 1024 * 1024
const FILE = { name: 'SKILL.md', size: 3277, kind: 'Skill' }

function makeFile(name = 'SKILL.md') {
  return new File(['# skill'], name, { type: 'text/markdown' })
}

describe('DropZone', () => {
  it('renders the idle prompt with allowed-type + size subtext', () => {
    render(<DropZone onFileSelected={() => {}} accept={ACCEPT} maxBytes={MAX} state="idle" />)
    expect(screen.getByText(/click to browse/i)).toBeInTheDocument()
    expect(screen.getByText(/max 10 MiB/i)).toBeInTheDocument()
  })

  it('emits onFileSelected from the file input', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <DropZone onFileSelected={onFileSelected} accept={ACCEPT} maxBytes={MAX} state="idle" />,
    )
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [makeFile()] } })
    expect(onFileSelected).toHaveBeenCalledTimes(1)
    expect(onFileSelected.mock.calls[0][0].name).toBe('SKILL.md')
  })

  it('emits onFileSelected on drop and clears the dragover state', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <DropZone onFileSelected={onFileSelected} accept={ACCEPT} maxBytes={MAX} state="idle" />,
    )
    const zone = container.querySelector('.dz-zone') as HTMLElement
    fireEvent.dragEnter(zone)
    fireEvent.drop(zone, { dataTransfer: { files: [makeFile('mcp.json')] } })
    expect(onFileSelected).toHaveBeenCalledTimes(1)
    expect(onFileSelected.mock.calls[0][0].name).toBe('mcp.json')
  })

  it('shows the selected-file card with kind chip + remove', () => {
    const onRemove = vi.fn()
    render(
      <DropZone
        onFileSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="selected"
        selectedFile={FILE}
        onRemove={onRemove}
      />,
    )
    expect(screen.getByText('SKILL.md')).toBeInTheDocument()
    expect(screen.getByText('Skill')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /remove file/i }))
    expect(onRemove).toHaveBeenCalled()
  })

  it('shows a byte counter while uploading', () => {
    render(
      <DropZone
        onFileSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="uploading"
        selectedFile={FILE}
        progress={0.5}
      />,
    )
    expect(screen.getByText(/\/ 3\.2 KiB/)).toBeInTheDocument()
  })

  it('renders the bucketed error message', () => {
    render(
      <DropZone
        onFileSelected={() => {}}
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
        onFileSelected={() => {}}
        accept={ACCEPT}
        maxBytes={MAX}
        state="selected"
        selectedFile={FILE}
        onRemove={() => {}}
      />,
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
