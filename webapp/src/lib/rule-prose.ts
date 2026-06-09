/**
 * Tiny shared transform for rubric prose, which (schema-constrained) only ever
 * contains inline `<code>…</code>` markup. A supply-chain product should never
 * ship arbitrary innerHTML, even for maintainer-authored text — so the methodology
 * card escapes everything and re-allows ONLY `<code>` (`renderInlineCode`), and the
 * CSV export strips the tags to plain text (`stripInlineCode`). One source of truth
 * for both so the on-page card and the exported row stay consistent.
 */

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Escape the whole string, then re-allow ONLY our own `<code>…</code>` delimiters.
 * Any other markup (and any byte inside the code span) stays escaped — safe to
 * `set:html`. The input is a trusted template that may carry inline `<code>`.
 */
export function renderInlineCode(value: string): string {
  return escapeHtml(value)
    .replace(/&lt;code&gt;/g, '<code>')
    .replace(/&lt;\/code&gt;/g, '</code>')
}

/** Drop the inline `<code>` tags, yielding plain text (for CSV cells / search). */
export function stripInlineCode(value: string): string {
  return value.replace(/<\/?code>/g, '')
}
