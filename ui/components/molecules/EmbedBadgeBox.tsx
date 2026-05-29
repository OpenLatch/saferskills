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
 * 3 tabs (Markdown / HTML / Preview). Markdown + HTML render the copy-pasteable
 * snippet; Preview renders the live SVG served by the Phase-C badge endpoint.
 * Origin resolves to the current site at runtime so the preview loads in dev.
 */
export default function EmbedBadgeBox({ scanId, score, slug, origin, onCopy }: Props) {
  const [format, setFormat] = useState<Format>('markdown')
  const resolvedOrigin =
    origin ?? (typeof window !== 'undefined' ? window.location.origin : 'https://saferskills.ai')
  const badgeUrl = `${resolvedOrigin}/badge/${scanId}/${score}.svg`
  const linkUrl = slug ? `${resolvedOrigin}/items/${slug}` : `${resolvedOrigin}/scans/${scanId}`

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
        <div className="embed-badge-box-preview">
          <img src={badgeUrl} alt={`SaferSkills score ${score} of 100`} width={280} height={60} />
          <span className="embed-badge-box-note">Live SVG — exactly what the badge URL serves.</span>
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
