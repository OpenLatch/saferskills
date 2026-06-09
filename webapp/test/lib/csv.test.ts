import { describe, expect, it } from 'vitest'
import { csvCell, toCsv } from '@/lib/csv'

describe('csvCell', () => {
  it('leaves a plain field unquoted', () => {
    expect(csvCell('hello')).toBe('hello')
  })

  it('quotes a field containing a comma', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
  })

  it('quotes and doubles an embedded double-quote', () => {
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
  })

  it('quotes a field with a newline', () => {
    expect(csvCell('line1\nline2')).toBe('"line1\nline2"')
  })

  it('quotes a field with a carriage return', () => {
    expect(csvCell('a\rb')).toBe('"a\rb"')
  })
})

describe('toCsv', () => {
  it('joins cells with commas and rows with CRLF', () => {
    expect(
      toCsv([
        ['a', 'b'],
        ['c', 'd'],
      ])
    ).toBe('a,b\r\nc,d')
  })

  it('quotes only the cells that need it', () => {
    const out = toCsv([
      ['name', 'note'],
      ['Prompt, injection', 'has "quotes"'],
    ])
    expect(out).toBe('name,note\r\n"Prompt, injection","has ""quotes"""')
  })
})
