import { useState } from 'react'

import CopyButton from '../atoms/CopyButton'

interface Props {
  scanId: string
  score: number
  slug?: string
  /** Base URL of the public site. Defaults to https://saferskills.ai */
  origin?: string
  /** PostHog callback per D-FE-19. */
  onCopy?: (format: 'markdown' | 'html' | 'preview') => void
}

type Format = 'markdown' | 'html' | 'preview'

/**
 * Embed-badge box shown on /scans/<id> + /items/<slug>.
 *
 * Phase B stub: 3 tabs (Markdown / HTML / Preview). Markdown + HTML render the
 * copy-pasteable snippet; Preview renders a placeholder span (live SVG ships
 * in Phase C with the badge endpoint).
 */
export default function EmbedBadgeBox({ scanId, score, slug, origin = 'https://saferskills.ai', onCopy }: Props) {
  const [format, setFormat] = useState<Format>('markdown')
  const badgeUrl = `${origin}/badge/${scanId}/${score}.svg`
  const linkUrl = slug ? `${origin}/items/${slug}` : `${origin}/scans/${scanId}`

  const snippets: Record<Format, string> = {
    markdown: `[![SaferSkills ${score}/100](${badgeUrl})](${linkUrl})`,
    html: `<a href="${linkUrl}"><img src="${badgeUrl}" alt="SaferSkills ${score}/100"></a>`,
    preview: '',
  }

  function handleSectionClick(e: React.MouseEvent<HTMLElement>) {
    if (!onCopy) return
    const target = e.target as HTMLElement
    if (target.closest('button[data-copy]')) onCopy(format)
  }

  return (
    <section className="embed-badge-box" aria-label="Embed badge" onClick={handleSectionClick}>
      <header className="embed-badge-box-head">
        <span className="eyebrow eyebrow-rule">EMBED · SAFERSKILLS BADGE</span>
        <div className="embed-badge-box-tabs" role="tablist">
          {(['markdown', 'html', 'preview'] as Format[]).map((f) => (
            <button
              key={f}
              type="button"
              className={format === f ? 'embed-badge-box-tab active' : 'embed-badge-box-tab'}
              onClick={() => setFormat(f)}
              role="tab"
              aria-selected={format === f}
            >
              {f}
            </button>
          ))}
        </div>
      </header>
      {format === 'preview' ? (
        <div className="embed-badge-box-preview" aria-label="Badge preview placeholder">
          <span className="embed-badge-box-placeholder">SaferSkills · {score}/100 — live preview ships Phase C</span>
        </div>
      ) : (
        <pre className="embed-badge-box-pre">
          <code>{snippets[format]}</code>
          <span data-copy>
            <CopyButton value={snippets[format]} label="Copy" />
          </span>
        </pre>
      )}
    </section>
  )
}
