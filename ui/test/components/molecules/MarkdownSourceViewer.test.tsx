import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import MarkdownSourceViewer from '../../../components/molecules/MarkdownSourceViewer'

const CONTENT = '# Title\n\nbody text'
const RENDERED = (
  <>
    <h1>Title</h1>
    <p>body text</p>
  </>
)

function setup() {
  return render(
    <MarkdownSourceViewer path="SKILL.md" bytes={2048} content={CONTENT} renderedHtml={RENDERED} />,
  )
}

describe('MarkdownSourceViewer', () => {
  it('renders the rendered view by default and shows path + bytes', () => {
    const { container } = setup()
    expect(container.querySelector('.md-body')).not.toBeNull()
    expect(container.querySelector('.md-raw')).toBeNull()
    expect(screen.getByText('SKILL.md')).toBeInTheDocument()
    // 2048 / 1024 = 2.0 KB
    expect(screen.getByText('2.0 KB · Markdown')).toBeInTheDocument()
  })

  it('toggles between Rendered and Raw', () => {
    const { container } = setup()
    fireEvent.click(screen.getByText('Raw'))
    expect(container.querySelector('.md-raw')?.textContent).toBe(CONTENT)
    expect(container.querySelector('.md-body')).toBeNull()
    fireEvent.click(screen.getByText('Rendered'))
    expect(container.querySelector('.md-body')).not.toBeNull()
    expect(container.querySelector('.md-raw')).toBeNull()
  })

  it('copies the raw content and flips the button label', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    setup()
    fireEvent.click(screen.getByText('⧉ Copy'))
    expect(writeText).toHaveBeenCalledWith(CONTENT)
    expect(await screen.findByText('✓ Copied')).toBeInTheDocument()
  })

  it('has no critical a11y violations', async () => {
    const { container } = setup()
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
