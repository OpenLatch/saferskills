import DOMPurify from 'dompurify'
import { marked } from 'marked'

interface Props {
  body: string
}

/**
 * Inline-sandboxed Markdown renderer for vendor responses + the compose-time
 * preview. `marked` → `DOMPurify` (browser DOM) with a tight allowlist: links
 * + basic formatting only, no images, no raw HTML, no scripts. Runs only in
 * the browser (the consuming islands are client-hydrated).
 */
export default function RenderMarkdown({ body }: Props) {
  const rawHtml = marked.parse(body, { async: false }) as string
  const clean = DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'a', 'ul', 'ol', 'li', 'blockquote'],
    ALLOWED_ATTR: ['href', 'title'],
    ALLOWED_URI_REGEXP: /^(https?:|mailto:)/i,
  })
  return (
    // biome-ignore lint/security/noDangerouslySetInnerHtml: sanitized by DOMPurify with a tight allowlist
    <div className="md-render" dangerouslySetInnerHTML={{ __html: clean }} />
  )
}
