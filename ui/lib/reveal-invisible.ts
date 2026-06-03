/**
 * Classify invisible / look-alike characters in a string so a report can reveal
 * them as visible glyph chips (the v3 `.ic.{zw,bidi,homo,space}` buckets).
 *
 * Pure + framework-agnostic. The caller renders each segment: `text` segments as
 * escaped React text, `mark` segments as a labelled `<span class="ic …">` chip.
 * Because the caller emits React nodes (never innerHTML), the revealed bytes
 * cannot break layout or inject markup — the security requirement for showing
 * verbatim scanned content.
 *
 * Codepoints are written as `\uXXXX` escapes (never literal invisible glyphs in
 * source — those are exactly what this module exists to surface).
 */

export type InvisibleClass = 'zw' | 'bidi' | 'homo' | 'space'

export type RevealSegment =
  | { kind: 'text'; text: string }
  | {
      kind: 'mark'
      cls: InvisibleClass
      /** Codepoint label, e.g. `U+200B`. */
      codepoint: string
      /** For homoglyphs: the original look-alike character (shown beside the cp). */
      glyph?: string
    }

function cp(code: number): string {
  return `U+${code.toString(16).toUpperCase().padStart(4, '0')}`
}

// Zero-width / formatting (zw), unusual space (space), and bidi-override (bidi).
const ZERO_WIDTH = [0x200b, 0x200c, 0x200d, 0x2060, 0xfeff]
const BIDI = [0x202a, 0x202b, 0x202c, 0x202d, 0x202e]
const SPACE = [0x00a0]
// Common Cyrillic homoglyphs that read as ASCII Latin letters (а→a, е→e, і→i, …).
const HOMOGLYPH = [0x0430, 0x0435, 0x0456, 0x043e, 0x0440, 0x0441, 0x0445]

const INVIS = new Map<string, { cls: InvisibleClass; codepoint: string }>()
for (const code of ZERO_WIDTH) INVIS.set(String.fromCharCode(code), { cls: 'zw', codepoint: cp(code) })
for (const code of BIDI) INVIS.set(String.fromCharCode(code), { cls: 'bidi', codepoint: cp(code) })
for (const code of SPACE) INVIS.set(String.fromCharCode(code), { cls: 'space', codepoint: cp(code) })

const HOMO = new Map<string, string>()
for (const code of HOMOGLYPH) HOMO.set(String.fromCharCode(code), cp(code))

/**
 * Split `text` into a sequence of plain-text runs and classified
 * invisible/look-alike marks. Adjacent plain characters coalesce into one
 * `text` segment.
 */
export function revealInvisible(text: string): RevealSegment[] {
  const out: RevealSegment[] = []
  let buf = ''
  const flush = () => {
    if (buf) {
      out.push({ kind: 'text', text: buf })
      buf = ''
    }
  }
  for (const ch of text) {
    const inv = INVIS.get(ch)
    if (inv) {
      flush()
      out.push({ kind: 'mark', cls: inv.cls, codepoint: inv.codepoint })
      continue
    }
    const homo = HOMO.get(ch)
    if (homo) {
      flush()
      out.push({ kind: 'mark', cls: 'homo', codepoint: homo, glyph: ch })
      continue
    }
    buf += ch
  }
  flush()
  return out
}

/** True if `text` contains any invisible / look-alike character. */
export function hasInvisible(text: string): boolean {
  for (const ch of text) {
    if (INVIS.has(ch) || HOMO.has(ch)) return true
  }
  return false
}
