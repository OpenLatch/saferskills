import type { Story } from '@ladle/react'

/**
 * DetectionTile — `.dt-tile` vocabulary.
 *
 * DetectionTile lives in the webapp package (`webapp/src/components/homepage/`),
 * so we mirror its markup here as plain React for Ladle visual review. CSS
 * contract lives in `webapp/src/styles/page-home.css::.dt-tile`.
 */
const TileMirror = ({
  sev,
  cat,
  title,
  hint,
  ruleId,
}: {
  sev: 'r' | 'o' | 'y' | 'g'
  cat: string
  title: string
  hint?: string
  ruleId?: string
}) => {
  const href = ruleId ? `/methodology#${ruleId}` : '#'
  return (
    <div className="detection-band" style={{ padding: 16, background: 'var(--color-paper)', display: 'inline-block' }}>
      <a className={`dt-tile sev-${sev}`} href={href}>
        <div className="dt-top">
          <span className="dt-cat">{cat}</span>
          <span className={`dt-sw sw-${sev}`} title={`Severity ${sev.toUpperCase()}`}></span>
        </div>
        <div className="dt-name">{title}</div>
        {hint && (
          <div className="dt-hint">
            <span className="dt-hint-arrow">▸</span>{hint}
          </div>
        )}
        <div className="dt-foot">
          <span className="dt-id">{ruleId ?? '—'}</span>
        </div>
      </a>
    </div>
  )
}

export const Orange: Story = () => (
  <TileMirror
    sev="o"
    cat="PROMPT INJECTION"
    title="Invisible Unicode Injection"
    hint="U+E0000–E007F"
    ruleId="SS-SKILL-INJECT-UNICODE-TAG-01"
  />
)

export const Red: Story = () => (
  <TileMirror
    sev="r"
    cat="RCE"
    title="curl ∣ bash"
    hint="curl/wget piped to bash/sh"
    ruleId="SS-HOOKS-RCE-CURL-PIPE-01"
  />
)

export const Yellow: Story = () => (
  <TileMirror
    sev="y"
    cat="TRANSPARENCY"
    title="Missing Changelog"
    hint="CHANGELOG.md absent"
    ruleId="SS-SKILL-TRANSPARENCY-CHANGELOG-01"
  />
)

export const Row: Story = () => (
  <div className="detection-band" style={{ padding: 16, background: 'var(--color-paper)' }}>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <a className="dt-tile sev-r" href="#">
        <div className="dt-top"><span className="dt-cat">RCE</span><span className="dt-sw sw-r"></span></div>
        <div className="dt-name">Destructive rm -rf</div>
        <div className="dt-hint"><span className="dt-hint-arrow">▸</span>rm -rf / $VAR ~</div>
        <div className="dt-foot"><span className="dt-id">SS-HOOKS-RCE-RMRF-01</span></div>
      </a>
      <a className="dt-tile sev-o" href="#">
        <div className="dt-top"><span className="dt-cat">SUPPLY CHAIN</span><span className="dt-sw sw-o"></span></div>
        <div className="dt-name">Typosquat Candidate</div>
        <div className="dt-hint"><span className="dt-hint-arrow">▸</span>Levenshtein ≤1</div>
        <div className="dt-foot"><span className="dt-id">SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01</span></div>
      </a>
      <a className="dt-tile sev-y" href="#">
        <div className="dt-top"><span className="dt-cat">COMMUNITY</span><span className="dt-sw sw-y"></span></div>
        <div className="dt-name">Single-Author Repo</div>
        <div className="dt-hint"><span className="dt-hint-arrow">▸</span>contributors = 1</div>
        <div className="dt-foot"><span className="dt-id">SS-SKILL-COMMUNITY-CONTRIBUTORS-01</span></div>
      </a>
    </div>
  </div>
)
