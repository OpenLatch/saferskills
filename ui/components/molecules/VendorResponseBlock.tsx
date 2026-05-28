interface Props {
  /** Markdown source — rendered as plain pre-wrapped text (Phase B stub; Phase C
   *  will swap in a sanitized markdown renderer). */
  bodyMarkdown: string
  /** Verified vendor display name (e.g. github org). */
  author: string
  /** ISO8601 timestamp; rendered as a relative date. */
  submittedAt: string
  /** Optional version label rendered next to the date. */
  version?: number
  /** Optional href for the vendor-response form (Phase C ships /respond). */
  respondHref?: string
}

function _formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

/**
 * Vendor right-of-reply block rendered on /scans/<id> + /items/<slug>.
 * Vocabulary: `mockups/hifi/app-pages.css::.vendor-response`. The maintainer
 * verifies via `.saferskills/verify.txt` and posts a markdown response capped
 * at 2000 chars (enforced in the backend via CHECK constraint).
 */
export default function VendorResponseBlock({
  bodyMarkdown,
  author,
  submittedAt,
  version,
  respondHref,
}: Props) {
  return (
    <section className="vendor-response" aria-label="Vendor response">
      <header className="vendor-response-head">
        <span className="eyebrow eyebrow-rule">VENDOR RESPONSE · 05</span>
        {version != null ? <span className="vendor-response-version">v{version}</span> : null}
      </header>
      <blockquote className="vendor-response-quote">
        <p className="vendor-response-body">{bodyMarkdown}</p>
        <cite className="vendor-response-cite">
          — <strong>{author}</strong>, {_formatDate(submittedAt)}
        </cite>
      </blockquote>
      {respondHref ? (
        <a className="vendor-response-respond" href={respondHref}>
          Are you the maintainer? Submit a response →
        </a>
      ) : null}
    </section>
  )
}
