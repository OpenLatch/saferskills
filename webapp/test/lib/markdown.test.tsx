import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/lib/markdown'

const html = (src: string): string => {
  const { container } = render(<div>{renderMarkdown(src)}</div>)
  return container.innerHTML
}

describe('renderMarkdown', () => {
  it('renders a linked badge ([![alt](img)](link)) as an anchor wrapping an image', () => {
    const out = html(
      '[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)'
    )
    expect(out).toContain('href="https://opensource.org/licenses/MIT"')
    expect(out).toContain('<img')
    expect(out).toContain('src="https://img.shields.io/badge/License-MIT-yellow.svg"')
    expect(out).toContain('alt="License: MIT"')
    // No raw markdown syntax leaks through.
    expect(out).not.toContain('![')
    expect(out).not.toContain('](')
  })

  it('renders a bare image', () => {
    const out = html('![logo](https://example.com/logo.png)')
    expect(out).toContain('<img')
    expect(out).toContain('src="https://example.com/logo.png"')
    expect(out).not.toContain('![')
  })

  it('renders an in-document anchor link and gives the heading a matching id', () => {
    const out = html('## Getting Started\n\n- [Getting Started](#getting-started)')
    expect(out).toContain('id="getting-started"')
    expect(out).toContain('href="#getting-started"')
    // Anchor links are same-page — not target=_blank.
    expect(out).not.toMatch(/href="#getting-started"[^>]*target/)
    expect(out).not.toContain('[Getting Started]')
  })

  it('renders a GFM table with header and body cells', () => {
    const src = [
      '| Category | Capabilities |',
      '|----------|-------------|',
      '| **Asset Management** | Browse, import |',
      '| Actor Control | Spawn, delete |',
    ].join('\n')
    const out = html(src)
    expect(out).toContain('<table')
    expect(out).toContain('<th>Category</th>')
    expect(out).toContain('<th>Capabilities</th>')
    expect(out).toContain('<strong>Asset Management</strong>')
    expect(out).toContain('<td>Spawn, delete</td>')
    expect(out).not.toContain('|---')
  })

  it('renders an external link as target=_blank with rel', () => {
    const out = html('[docs](https://example.com/docs)')
    expect(out).toContain('href="https://example.com/docs"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener noreferrer"')
  })

  it('rejects dangerous schemes — javascript: link renders as plain text', () => {
    const out = html('[click](javascript:alert(1))')
    expect(out).not.toContain('<a')
    expect(out).not.toContain('javascript:')
    expect(out).toContain('click')
  })

  it('falls back to alt text for a non-http image source', () => {
    const out = html('![diagram](data:image/png;base64,AAAA)')
    expect(out).not.toContain('<img')
    expect(out).toContain('diagram')
  })
})
