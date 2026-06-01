import { useState } from 'react'

interface Props {
  slug: string
  installsTotal: number
  latestVersion: string | null
  githubUrl: string
}

/**
 * Item-detail sidebar Install card — the `npx saferskills install` command with
 * a copy button, a Download .zip (GitHub archive — Phase A; a SaferSkills-served
 * artifact lands in Phase C), and the install count.
 */
export default function InstallCard({ slug, installsTotal, latestVersion, githubUrl }: Props) {
  const [copied, setCopied] = useState(false)
  const command = `npx saferskills install ${slug} --to claude-code`
  const downloadUrl = latestVersion
    ? `${githubUrl}/archive/refs/tags/${latestVersion}.zip`
    : `${githubUrl}/archive/HEAD.zip`

  return (
    <div className="side-card install-card">
      <h4>Install via SaferSkills</h4>
      <div className="cmd">
        <span className="pr">$</span>
        <span className="ctext">npx saferskills install {slug}</span>
        <span className="arg">--to claude-code</span>
        <button
          type="button"
          className="copy-mini"
          aria-label="Copy install command"
          onClick={() => {
            navigator.clipboard?.writeText(command)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          }}
        >
          {copied ? '✓' : '⧉'}
        </button>
      </div>
      <p className="install-note">
        {latestVersion
          ? `Re-verifies the ${latestVersion} score at install time`
          : 'Re-verifies the score at install time'}{' '}
        · one binary across all 8 agents.
      </p>
      <div className="install-cta">
        <a className="btn primary sm" href={downloadUrl} target="_blank" rel="noopener">
          ⤓ Download .zip
        </a>
        <span className="zip-meta">
          {`${slug}${latestVersion ? `-${latestVersion}` : ''}.zip`} · via GitHub
        </span>
      </div>
      <div className="install-count">
        <span className="ic-num">{installsTotal.toLocaleString()}</span>
        <span className="ic-lbl">installs via SaferSkills</span>
      </div>
    </div>
  )
}
