import { describe, expect, it } from 'vitest'

import { hasInvisible, revealInvisible } from '../../lib/reveal-invisible'

// Build the test glyphs from codepoints — never literal invisible chars in source.
const ZWSP = String.fromCharCode(0x200b)
const RLO = String.fromCharCode(0x202e)
const NBSP = String.fromCharCode(0x00a0)
const CYR_I = String.fromCharCode(0x0456) // Cyrillic і — homoglyph of ASCII i

describe('revealInvisible', () => {
  it('returns a single text segment for plain ASCII', () => {
    expect(revealInvisible('hello world')).toEqual([{ kind: 'text', text: 'hello world' }])
  })

  it('classifies a zero-width space as a zw mark', () => {
    expect(revealInvisible(`a${ZWSP}b`)).toEqual([
      { kind: 'text', text: 'a' },
      { kind: 'mark', cls: 'zw', codepoint: 'U+200B' },
      { kind: 'text', text: 'b' },
    ])
  })

  it('classifies a bidi override as a bidi mark', () => {
    expect(revealInvisible(`x${RLO}y`)[1]).toEqual({
      kind: 'mark',
      cls: 'bidi',
      codepoint: 'U+202E',
    })
  })

  it('classifies a non-breaking space as a space mark', () => {
    expect(revealInvisible(`a${NBSP}b`)[1]).toEqual({
      kind: 'mark',
      cls: 'space',
      codepoint: 'U+00A0',
    })
  })

  it('classifies a Cyrillic homoglyph and keeps the original glyph', () => {
    expect(revealInvisible(`reg${CYR_I}stry`)).toContainEqual({
      kind: 'mark',
      cls: 'homo',
      codepoint: 'U+0456',
      glyph: CYR_I,
    })
  })

  it('coalesces adjacent plain characters around marks', () => {
    const segs = revealInvisible(`ab${ZWSP}cd`)
    expect(segs.map((s) => s.kind)).toEqual(['text', 'mark', 'text'])
    expect(segs[0]).toEqual({ kind: 'text', text: 'ab' })
    expect(segs[2]).toEqual({ kind: 'text', text: 'cd' })
  })
})

describe('hasInvisible', () => {
  it('is false for plain ASCII', () => {
    expect(hasInvisible('deploy now')).toBe(false)
  })
  it('is true when a zero-width or homoglyph is present', () => {
    expect(hasInvisible(`deploy${ZWSP}now`)).toBe(true)
    expect(hasInvisible(`reg${CYR_I}stry`)).toBe(true)
  })
})
