import { describe, expect, it } from 'vitest'

import { capabilityAppJsonLd, serializeJsonLd } from '@/lib/jsonld'

// SEO-T4 XSS guard. A scanned repo's name / author / slug is attacker-controlled
// (anonymous submissions flow straight into `capabilityAppJsonLd`). The renderer
// (`components/seo/JsonLd.astro`) emits the output of `serializeJsonLd` verbatim
// via `set:html`, so the escaping MUST neutralize a `</script>` break-out and the
// JS-string-invalid U+2028 / U+2029 separators before they reach the DOM.
const LS = String.fromCharCode(0x2028)
const PS = String.fromCharCode(0x2029)

describe('serializeJsonLd — XSS escaping', () => {
  it('escapes a </script> break-out in an attacker-controlled name', () => {
    const malicious = capabilityAppJsonLd({
      slug: 'evil',
      name: '</script><script>alert(1)</script>',
      kind: 'skill',
    })
    const out = serializeJsonLd(malicious)
    // No raw `<` survives — every one is escaped to <, so the string can
    // never close the host <script> element or open a new one. (Escaping `<`
    // alone is sufficient; `>` is harmless without a preceding `<`.)
    expect(out).not.toContain('<')
    expect(out).not.toContain('</script>')
    expect(out).toContain('\\u003c/script>')
    // Still valid JSON that round-trips back to the original name.
    const parsed = JSON.parse(out)
    expect(parsed.name).toBe('</script><script>alert(1)</script>')
  })

  it('escapes U+2028 / U+2029 separators (invalid inside a JS string)', () => {
    const malicious = capabilityAppJsonLd({
      slug: 'sep',
      name: `line${LS}sep${PS}para`,
      kind: 'skill',
    })
    const out = serializeJsonLd(malicious)
    expect(out).not.toContain(LS)
    expect(out).not.toContain(PS)
    expect(out).toContain('\\u2028')
    expect(out).toContain('\\u2029')
    const parsed = JSON.parse(out)
    expect(parsed.name).toBe(`line${LS}sep${PS}para`)
  })
})
