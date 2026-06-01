import type { ReactNode } from 'react'

/**
 * Minimal, XSS-safe Markdown → React renderer for the item-detail Source tab.
 *
 * Manifest content is untrusted (arbitrary public repo file), so we render to
 * React nodes — never `dangerouslySetInnerHTML` (per `.claude/rules/frontend-patterns.md`).
 * Supports the subset a SKILL.md uses: YAML frontmatter block, ATX headings,
 * fenced code, blockquotes, ordered/unordered lists, `hr`, and inline
 * **bold** / *italic* / `code` / [links](http…). Links are restricted to
 * http(s) hrefs; everything else renders as plain text.
 */

let keySeq = 0
function k(): string {
  keySeq += 1
  return `md-${keySeq}`
}

/** Inline spans: `code`, **bold**, *italic*, [text](http…). */
function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  // Tokenize on the inline markers, left to right.
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g
  let last = 0
  let m: RegExpExecArray | null
  // biome-ignore lint/suspicious/noAssignInExpressions: standard regex walk
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) {
      out.push(<code key={k()}>{tok.slice(1, -1)}</code>)
    } else if (tok.startsWith('**')) {
      out.push(<strong key={k()}>{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('*')) {
      out.push(<em key={k()}>{tok.slice(1, -1)}</em>)
    } else {
      const label = tok.slice(1, tok.indexOf(']'))
      const href = m[2]
      out.push(
        <a key={k()} href={href} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      )
    }
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function renderMarkdown(src: string): ReactNode[] {
  keySeq = 0
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0

  // Optional leading YAML frontmatter.
  if (lines[0]?.trim() === '---') {
    const fm: string[] = []
    i = 1
    while (i < lines.length && lines[i].trim() !== '---') {
      fm.push(lines[i])
      i++
    }
    i++ // closing ---
    blocks.push(
      <div className="md-fm" key={k()}>
        {fm.map((line) => {
          const idx = line.indexOf(':')
          if (idx === -1) return <div key={k()}>{line}</div>
          return (
            <div key={k()}>
              <span className="k">{line.slice(0, idx)}</span>
              {line.slice(idx)}
            </div>
          )
        })}
      </div>
    )
  }

  let para: string[] = []
  const flushPara = () => {
    if (para.length) {
      blocks.push(<p key={k()}>{renderInline(para.join(' '))}</p>)
      para = []
    }
  }

  while (i < lines.length) {
    const line = lines[i]
    const t = line.trim()

    if (t.startsWith('```')) {
      flushPara()
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        code.push(lines[i])
        i++
      }
      i++ // closing fence
      blocks.push(
        <pre key={k()}>
          <code>{code.join('\n')}</code>
        </pre>
      )
      continue
    }
    if (t === '---' || t === '***') {
      flushPara()
      blocks.push(<hr key={k()} />)
      i++
      continue
    }
    if (t.startsWith('### ')) {
      flushPara()
      blocks.push(<h3 key={k()}>{renderInline(t.slice(4))}</h3>)
      i++
      continue
    }
    if (t.startsWith('## ')) {
      flushPara()
      blocks.push(<h2 key={k()}>{renderInline(t.slice(3))}</h2>)
      i++
      continue
    }
    if (t.startsWith('# ')) {
      flushPara()
      blocks.push(<h1 key={k()}>{renderInline(t.slice(2))}</h1>)
      i++
      continue
    }
    if (t.startsWith('> ')) {
      flushPara()
      const quote: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('> ')) {
        quote.push(lines[i].trim().slice(2))
        i++
      }
      blocks.push(<blockquote key={k()}>{renderInline(quote.join(' '))}</blockquote>)
      continue
    }
    if (/^[-*]\s+/.test(t)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ''))
        i++
      }
      blocks.push(
        <ul key={k()}>
          {items.map((it) => (
            <li key={k()}>{renderInline(it)}</li>
          ))}
        </ul>
      )
      continue
    }
    if (/^\d+\.\s+/.test(t)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push(
        <ol key={k()}>
          {items.map((it) => (
            <li key={k()}>{renderInline(it)}</li>
          ))}
        </ol>
      )
      continue
    }
    if (t === '') {
      flushPara()
      i++
      continue
    }
    para.push(t)
    i++
  }
  flushPara()
  return blocks
}
