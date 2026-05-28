import { describe, expect, it } from 'vitest'
import { isPlatformShortcut } from '../../hooks/use-focus-shortcut'

function evt(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

describe('isPlatformShortcut', () => {
  it('matches Cmd+K on macOS', () => {
    expect(isPlatformShortcut(evt({ metaKey: true, key: 'k' }), 'k')).toBe(true)
  })

  it('matches Ctrl+K on Windows / Linux', () => {
    expect(isPlatformShortcut(evt({ ctrlKey: true, key: 'k' }), 'k')).toBe(true)
  })

  it('matches case-insensitively', () => {
    expect(isPlatformShortcut(evt({ metaKey: true, key: 'K' }), 'k')).toBe(true)
    expect(isPlatformShortcut(evt({ ctrlKey: true, key: 'k' }), 'K')).toBe(true)
  })

  it('does not match plain K', () => {
    expect(isPlatformShortcut(evt({ key: 'k' }), 'k')).toBe(false)
  })

  it('does not match Cmd+Shift+K (chord conflict guard)', () => {
    expect(isPlatformShortcut(evt({ metaKey: true, shiftKey: true, key: 'k' }), 'k')).toBe(false)
  })

  it('does not match Cmd+Alt+K', () => {
    expect(isPlatformShortcut(evt({ metaKey: true, altKey: true, key: 'k' }), 'k')).toBe(false)
  })

  it('does not match a different letter', () => {
    expect(isPlatformShortcut(evt({ metaKey: true, key: 'j' }), 'k')).toBe(false)
  })
})
