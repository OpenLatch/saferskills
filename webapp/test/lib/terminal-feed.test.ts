import { describe, expect, it } from 'vitest'
import { buildTerminalLines, type FeedEvent, formatTarget } from '@/components/scan/terminal-feed'

describe('formatTarget', () => {
  it('returns host-relative + ref for a github tree URL', () => {
    expect(formatTarget('https://github.com/anthropics/skills/tree/main')).toEqual({
      host: 'github.com/anthropics/skills',
      ref: 'main',
    })
  })

  it('has no ref for a bare repo URL', () => {
    expect(formatTarget('https://github.com/anthropics/skills')).toEqual({
      host: 'github.com/anthropics/skills',
      ref: undefined,
    })
  })

  it('passes a non-URL upload name through as the host', () => {
    expect(formatTarget('skills.zip')).toEqual({ host: 'skills.zip' })
  })

  it('renders an em-dash for an empty target', () => {
    expect(formatTarget()).toEqual({ host: '—' })
  })
})

describe('buildTerminalLines', () => {
  const target = 'https://github.com/acme/x/tree/main'

  it('always begins with the command line carrying the host', () => {
    const lines = buildTerminalLines([], target)
    expect(lines[0]).toMatchObject({ id: 'cmd', kind: 'cmd' })
    expect(lines[0].segments.map((s) => s.text).join('')).toContain('github.com/acme/x')
  })

  it('maps a rule event to a detector line within its stage', () => {
    const events: FeedEvent[] = [
      {
        stage: 'security',
        status: 'running',
        payload: { rule_id: 'SS-SKILL-INJECT-FENCED-RUN-02', target: 'SKILL.md' },
      },
    ]
    const detector = buildTerminalLines(events, target).find((l) => l.id.startsWith('rule:'))
    expect(detector?.kind).toBe('run')
    expect(detector?.segments).toContainEqual({
      text: 'SS-SKILL-INJECT-FENCED-RUN-02',
      tone: 'rule',
    })
    expect(detector?.segments).toContainEqual({ text: 'SKILL.md', tone: 'path' })
  })

  it('renders stage start + complete lines', () => {
    const events: FeedEvent[] = [
      { stage: 'fetch', status: 'running' },
      { stage: 'fetch', status: 'completed' },
    ]
    const lines = buildTerminalLines(events, target)
    expect(lines.some((l) => l.kind === 'run' && l.segments[0].text === 'Fetch')).toBe(true)
    expect(lines.some((l) => l.kind === 'ok' && l.segments[0].text === 'Fetch complete')).toBe(true)
  })

  it('de-duplicates repeated progress ticks for the same stage + status', () => {
    const events: FeedEvent[] = [
      { stage: 'security', status: 'running' },
      { stage: 'security', status: 'running' },
      { stage: 'security', status: 'running' },
    ]
    const lines = buildTerminalLines(events, target)
    expect(lines.filter((l) => l.id === 'stage:security:running')).toHaveLength(1)
  })

  it('emits the terminal "done" line on a completed done stage', () => {
    const lines = buildTerminalLines([{ stage: 'done', status: 'completed' }], target)
    expect(lines.some((l) => l.kind === 'done')).toBe(true)
  })
})
