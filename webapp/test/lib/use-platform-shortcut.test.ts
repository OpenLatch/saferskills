import { describe, expect, it } from 'vitest'
import { detectIsMac, formatShortcut } from '../../src/lib/use-platform-shortcut'

describe('detectIsMac', () => {
  it('returns true for Mac platforms', () => {
    expect(detectIsMac('MacIntel')).toBe(true)
    expect(detectIsMac('MacPPC')).toBe(true)
    expect(detectIsMac('macOS')).toBe(true)
  })

  it('returns false for non-Mac platforms', () => {
    expect(detectIsMac('Win32')).toBe(false)
    expect(detectIsMac('Linux x86_64')).toBe(false)
    expect(detectIsMac('iPhone')).toBe(false)
  })

  it('handles empty / undefined input', () => {
    expect(detectIsMac('')).toBe(false)
    expect(detectIsMac(undefined)).toBe(false)
  })
})

describe('formatShortcut', () => {
  it('renders Mac labels with the command glyph', () => {
    expect(formatShortcut('K', true)).toBe('⌘K')
    expect(formatShortcut('j', true)).toBe('⌘J')
  })

  it('renders Windows / Linux labels with Ctrl+', () => {
    expect(formatShortcut('K', false)).toBe('Ctrl+K')
    expect(formatShortcut('j', false)).toBe('Ctrl+J')
  })
})
