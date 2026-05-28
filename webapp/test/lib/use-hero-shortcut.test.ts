import { describe, expect, it } from 'vitest'
import { isHeroShortcut } from '../../src/lib/use-hero-shortcut'

function evt(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

describe('isHeroShortcut', () => {
  it('matches Cmd+K on macOS', () => {
    expect(isHeroShortcut(evt({ metaKey: true, key: 'k' }), 'k')).toBe(true)
  })

  it('matches Ctrl+K on Windows / Linux', () => {
    expect(isHeroShortcut(evt({ ctrlKey: true, key: 'k' }), 'k')).toBe(true)
  })

  it('matches case-insensitively', () => {
    expect(isHeroShortcut(evt({ metaKey: true, key: 'K' }), 'k')).toBe(true)
    expect(isHeroShortcut(evt({ ctrlKey: true, key: 'k' }), 'K')).toBe(true)
  })

  it('does not match plain K', () => {
    expect(isHeroShortcut(evt({ key: 'k' }), 'k')).toBe(false)
  })

  it('does not match Cmd+Shift+K (chord conflict guard)', () => {
    expect(isHeroShortcut(evt({ metaKey: true, shiftKey: true, key: 'k' }), 'k')).toBe(false)
  })

  it('does not match Cmd+Alt+K', () => {
    expect(isHeroShortcut(evt({ metaKey: true, altKey: true, key: 'k' }), 'k')).toBe(false)
  })

  it('does not match a different letter', () => {
    expect(isHeroShortcut(evt({ metaKey: true, key: 'j' }), 'k')).toBe(false)
  })
})
