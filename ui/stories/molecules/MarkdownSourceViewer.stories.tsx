import type { Story } from '@ladle/react'
import MarkdownSourceViewer from '../../components/molecules/MarkdownSourceViewer'

const SAMPLE = `# pdf-extract

A skill that extracts text from PDF files.

## Usage

Call the skill with a path to a PDF.
`

// In the app, the caller passes renderMarkdown(content); here we hand-roll a
// minimal rendered tree so the story stays renderer-agnostic.
const RENDERED = (
  <>
    <h1>pdf-extract</h1>
    <p>A skill that extracts text from PDF files.</p>
    <h2>Usage</h2>
    <p>Call the skill with a path to a PDF.</p>
  </>
)

export const Default: Story = () => (
  <div style={{ maxWidth: 760, padding: 40 }}>
    <MarkdownSourceViewer path="SKILL.md" bytes={1843} content={SAMPLE} renderedHtml={RENDERED} />
  </div>
)

export const LongPath: Story = () => (
  <div style={{ maxWidth: 760, padding: 40 }}>
    <MarkdownSourceViewer
      path=".claude/skills/pdf-extract/SKILL.md"
      bytes={512}
      content={SAMPLE}
      renderedHtml={RENDERED}
    />
  </div>
)
