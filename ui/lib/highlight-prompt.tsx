import type { ReactNode } from 'react'

/**
 * Lightweight syntax tinter for the SaferSkills Agent-Scan bootstrap prompt
 * shown in `PromptCodeCard` (the `tinted` prop). It restores the v3 mockup's
 * `.tok-*` coloring that was dropped when the `.code-editor` block became the
 * generic `PromptCodeCard` — without pulling in a real highlighter.
 *
 * It tints by pattern, so it works for BOTH the `{{…}}` template preview and
 * the minted prompt (where the placeholders become real URLs/tokens). Output is
 * built from React text nodes + `className`-only spans — never `innerHTML` — so
 * verbatim prompt bytes (real run tokens / URLs) cannot inject markup.
 *
 * Token classes (`.pc-tok-*`, dark palette in `ui/styles/components.css`):
 *   c comment · k keyword/verb · s string/url · f header/fn · m module/result
 */

type Tok = 'k' | 's' | 'f' | 'm'

interface Rule {
  re: RegExp
  tok: Tok
}

// Ordered by priority — when two matches start at the same index the earlier
// rule wins; otherwise the earliest start wins (greedy, non-overlapping).
const RULES: readonly Rule[] = [
  { re: /\*\*[^*]+\*\*/g, tok: 'm' }, // **SaferSkills Agent Scan**
  { re: /\bagent_scan_result\.v1\b/g, tok: 'm' }, // the result envelope type
  { re: /\{\{[^}]+\}\}/g, tok: 's' }, // {{PACK_URL}} / {{RUN_TOKEN}} / {{SUBMIT_URL}}
  { re: /https?:\/\/[^\s"')]+/g, tok: 's' }, // real URLs once minted
  { re: /\bX-[A-Za-z0-9-]+\b/g, tok: 'f' }, // X-SaferSkills-Run-Token, X-Pack-*
  { re: /\bContent-Type\b/g, tok: 'f' },
  { re: /\bcurl\b/g, tok: 'f' },
  { re: /\b(?:GET|POST|PUT|PATCH|DELETE)\b/g, tok: 'k' }, // HTTP verbs
  { re: /"[A-Za-z_][A-Za-z0-9_]*"/g, tok: 's' }, // "instructions"
  { re: /\bsaferskills\.ai\b/g, tok: 's' },
]

interface Match {
  start: number
  end: number
  tok: Tok
  prio: number
}

/** A line is "code"-tinted; the trailing Privacy paragraph is whole-line comment. */
function tintLine(line: string, keyBase: number): ReactNode {
  if (line === '') return ''
  const matches: Match[] = []

  // Leading step number ("1." / "2." / "3.") → keyword, ahead of every rule.
  const step = /^(\s*)(\d+\.)(?=\s|$)/.exec(line)
  if (step) {
    const start = step[1].length
    matches.push({ start, end: start + step[2].length, tok: 'k', prio: -1 })
  }

  RULES.forEach((rule, prio) => {
    rule.re.lastIndex = 0
    let m: RegExpExecArray | null = rule.re.exec(line)
    while (m !== null) {
      matches.push({ start: m.index, end: m.index + m[0].length, tok: rule.tok, prio })
      m = rule.re.exec(line)
    }
  })

  if (matches.length === 0) return line

  matches.sort((a, b) => a.start - b.start || a.prio - b.prio)

  const out: ReactNode[] = []
  let cursor = 0
  let k = 0
  for (const mt of matches) {
    if (mt.start < cursor) continue // overlaps an already-picked match
    if (mt.start > cursor) out.push(line.slice(cursor, mt.start))
    out.push(
      // biome-ignore lint/suspicious/noArrayIndexKey: positional token segments
      <span key={`${keyBase}-${k}`} className={`pc-tok-${mt.tok}`}>
        {line.slice(mt.start, mt.end)}
      </span>,
    )
    k++
    cursor = mt.end
  }
  if (cursor < line.length) out.push(line.slice(cursor))
  return out
}

/**
 * Tint every prompt line. The trailing Privacy paragraph (from the first line
 * starting with "Privacy:" to the end) is rendered as whole-line comments; all
 * other lines are pattern-tinted. Returns one ReactNode per input line, aligned
 * 1:1 so the caller can render it inside its line rows.
 */
export function highlightAgentPrompt(lines: readonly string[]): ReactNode[] {
  let inComment = false
  return lines.map((line, i) => {
    if (!inComment && line.trimStart().startsWith('Privacy:')) inComment = true
    if (inComment) {
      return line === '' ? (
        ''
      ) : (
        <span key={i} className="pc-tok-c">
          {line}
        </span>
      )
    }
    return tintLine(line, i)
  })
}
