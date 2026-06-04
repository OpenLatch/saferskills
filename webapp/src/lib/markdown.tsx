import { Fragment, type ReactNode } from 'react'

/**
 * Minimal, XSS-safe Markdown → React renderer for the item-detail Source tab.
 *
 * Manifest content is untrusted (arbitrary public repo file), so we render to
 * React nodes — never `dangerouslySetInnerHTML` (per `.claude/rules/frontend-patterns.md`).
 * Supports the subset a README / SKILL.md uses: YAML frontmatter block, ATX
 * headings (with anchor IDs so a Table-of-Contents `[x](#x)` jumps), fenced
 * code, blockquotes, ordered/unordered lists, GFM tables, `hr`, and inline
 * **bold** / *italic* / `code` / images / [links](…) / [![badge](img)](link).
 *
 * Security: link hrefs allow only http(s) / mailto / anchors / relative paths
 * (any `javascript:` / `data:` / other scheme renders as plain text); image
 * sources allow only http(s) (else the alt text renders).
 */

let keySeq = 0
function k(): string {
  keySeq += 1
  return `md-${keySeq}`
}

/** GitHub-style heading slug for in-document anchor links. */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
}

/** Allow http(s) / mailto / #anchor / relative; reject javascript:, data:, etc. */
function isSafeHref(href: string): boolean {
  const u = href.trim()
  // A leading scheme (e.g. `javascript:`) — permit only http(s) and mailto.
  if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return /^(https?:|mailto:)/i.test(u)
  // No scheme: anchor (#…), absolute (/…) or relative path — safe.
  return true
}

const isHttp = (url: string): boolean => /^https?:\/\//i.test(url.trim())

function renderImage(alt: string, src: string): ReactNode {
  if (!isHttp(src)) return <Fragment key={k()}>{alt}</Fragment>
  // referrerPolicy keeps the catalog URL out of badge-server logs.
  return (
    <img
      key={k()}
      className="md-img"
      src={src}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
    />
  )
}

function renderLink(label: string, href: string, children?: ReactNode): ReactNode {
  if (!isSafeHref(href)) return <Fragment key={k()}>{children ?? label}</Fragment>
  const external = isHttp(href)
  const isImg = children != null
  return (
    <a
      key={k()}
      className={isImg ? 'md-img-link' : undefined}
      href={href}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {children ?? renderInline(label)}
    </a>
  )
}

// One pass, leftmost match. Order matters: linked-image and image are tried
// before a plain link so `[![…](img)](link)` and `![…](…)` win over `[…](…)`.
const INLINE_PATTERN =
  '(`[^`]+`|\\*\\*[^*]+\\*\\*|\\*[^*]+\\*|\\[!\\[[^\\]]*\\]\\([^)\\s]+\\)\\]\\([^)\\s]+\\)|!\\[[^\\]]*\\]\\([^)\\s]+\\)|\\[[^\\]]+\\]\\([^)\\s]+\\))'

/** Inline spans: `code`, **bold**, *italic*, images, links, linked badges. */
function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  // A fresh regex per call: `renderInline` recurses (a link label re-enters it),
  // so a shared /g regex's `lastIndex` would be clobbered mid-walk.
  const re = new RegExp(INLINE_PATTERN, 'g')
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
    } else if (tok.startsWith('[![')) {
      const mm = /^\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)$/.exec(tok)
      if (mm) out.push(renderLink(mm[1], mm[3], renderImage(mm[1], mm[2])))
    } else if (tok.startsWith('![')) {
      const mm = /^!\[([^\]]*)\]\(([^)\s]+)\)$/.exec(tok)
      if (mm) out.push(renderImage(mm[1], mm[2]))
    } else {
      const mm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok)
      if (mm) out.push(renderLink(mm[1], mm[2]))
    }
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

/** Split a GFM table row into trimmed cells, dropping outer pipes. */
function splitRow(line: string): string[] {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|')) s = s.slice(0, -1)
  return s.split('|').map((c) => c.trim())
}

/** A `|---|:--:|` delimiter row marks the line above as a table header. */
function isTableDelimiter(line: string): boolean {
  const t = line.trim()
  return t.includes('-') && /^\|?[\s:|-]+\|?$/.test(t)
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
      const txt = t.slice(4)
      blocks.push(
        <h3 key={k()} id={slugify(txt)}>
          {renderInline(txt)}
        </h3>
      )
      i++
      continue
    }
    if (t.startsWith('## ')) {
      flushPara()
      const txt = t.slice(3)
      blocks.push(
        <h2 key={k()} id={slugify(txt)}>
          {renderInline(txt)}
        </h2>
      )
      i++
      continue
    }
    if (t.startsWith('# ')) {
      flushPara()
      const txt = t.slice(2)
      blocks.push(
        <h1 key={k()} id={slugify(txt)}>
          {renderInline(txt)}
        </h1>
      )
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
    // GFM table: a `| … |` header row immediately followed by a `|---|` row.
    if (t.startsWith('|') && i + 1 < lines.length && isTableDelimiter(lines[i + 1])) {
      flushPara()
      const header = splitRow(t)
      i += 2 // header + delimiter
      const rows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]))
        i++
      }
      blocks.push(
        <div className="md-tablewrap" key={k()}>
          <table className="md-table">
            <thead>
              <tr>
                {header.map((cell) => (
                  <th key={k()}>{renderInline(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={k()}>
                  {row.map((cell) => (
                    <td key={k()}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
