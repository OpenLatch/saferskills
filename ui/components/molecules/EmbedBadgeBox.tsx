import Toast, { flashToast } from '../atoms/Toast'

type Tier = 'green' | 'yellow' | 'orange' | 'red'

interface Props {
  scanId: string
  score: number
  /** Scored tier; colors the preview pill. null/undefined → unscored. */
  tier?: Tier | null
  slug?: string
  /** Base URL of the public site. Defaults to https://saferskills.ai */
  origin?: string
  /**
   * Badge family. `scan` (default) → `/badge/{id}/{score}.svg` + `/scans/{id}`
   * (or `/items/{slug}`). `agent` → `/badge/agent/{id}/{score}.svg` +
   * `/agents/{id}` (the I-5.6 Agent Report badge — D-5.6-14, Codex P2).
   */
  kind?: 'scan' | 'agent'
  /** Alt-text/preview noun. Defaults to `SaferSkills`. */
  altPrefix?: string
  /** PostHog callback per D-FE-19. */
  onCopy?: (format: 'markdown' | 'html') => void
}

/**
 * Embed-badge box shown on /scans/<id> + /items/<slug>.
 *
 * Renders a macOS terminal window (README.md chrome) with the syntax-colored
 * markdown snippet + two header copy buttons ("⧉ Copy to MD" / "⧉ Copy as
 * HTML"), then a CSS-rendered badge pill preview. The preview is a pure-CSS
 * pill (no network fetch) so it always renders, including for upload runs whose
 * badge SVG 404s.
 */
export default function EmbedBadgeBox({
  scanId,
  score,
  tier,
  slug,
  origin,
  kind = 'scan',
  altPrefix = 'SaferSkills',
  onCopy,
}: Props) {
  const resolvedOrigin =
    origin ?? (typeof window !== 'undefined' ? window.location.origin : 'https://saferskills.ai')
  const isAgent = kind === 'agent'
  const badgeUrl = isAgent
    ? `${resolvedOrigin}/badge/agent/${scanId}/${score}.svg`
    : `${resolvedOrigin}/badge/${scanId}/${score}.svg`
  const linkUrl = isAgent
    ? `${resolvedOrigin}/agents/${scanId}`
    : slug
      ? `${resolvedOrigin}/items/${slug}`
      : `${resolvedOrigin}/scans/${scanId}`

  const markdown = `[![${altPrefix} ${score}/100](${badgeUrl})](${linkUrl})`
  const html = `<a href="${linkUrl}"><img src="${badgeUrl}" alt="${altPrefix} ${score}/100"></a>`

  async function copy(format: 'markdown' | 'html', snippet: string) {
    onCopy?.(format)
    try {
      await navigator.clipboard.writeText(snippet)
      flashToast('Copied to clipboard')
    } catch {
      flashToast('Copy failed — please copy manually')
    }
  }

  return (
    <div className="embed-badge" aria-label="Embed README badge">
      <div className="badge-term">
        <div className="bt-chrome">
          <span className="mac-traffic">
            <span className="l-r" />
            <span className="l-y" />
            <span className="l-g" />
          </span>
          <span className="bt-title">README.md</span>
          <div className="bt-copy-group">
            <button type="button" className="bt-copy" onClick={() => copy('markdown', markdown)}>
              <span aria-hidden="true">⧉</span> Copy to MD
            </button>
            <button type="button" className="bt-copy" onClick={() => copy('html', html)}>
              <span aria-hidden="true">⧉</span> Copy as HTML
            </button>
          </div>
        </div>
        <div className="bt-body">
          <code>
            <span className="md-punc">[![</span>
            <span className="md-alt">
              {altPrefix} {score}/100
            </span>
            <span className="md-punc">](</span>
            <span className="md-url">{badgeUrl}</span>
            <span className="md-punc">)](</span>
            <span className="md-link">{linkUrl}</span>
            <span className="md-punc">)</span>
          </code>
        </div>
      </div>
      <div className="bt-actions">
        <div className={`badge-preview tier-${tier ?? 'unscoped'}`} aria-label="Badge preview">
          <span className="lf">saferskills</span>
          <span className="rg">
            {score} · {tier ?? 'unscored'}
          </span>
        </div>
      </div>
      <Toast />
    </div>
  )
}
