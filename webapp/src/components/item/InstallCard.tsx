import { useState } from 'react'

import { type DownloadInfo, itemDownloadUrl } from '@/lib/api/items'

interface Props {
  slug: string
  installsTotal: number
  latestVersion: string | null
  githubUrl: string
  download?: DownloadInfo | null
}

function fmtBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

/**
 * Item-detail sidebar Install card — the `npx saferskills install` command with
 * a copy button, a Download .zip, and the install count. The download serves the
 * SaferSkills-stored snapshot when one exists (real byte size + "SaferSkills"),
 * falling back to the GitHub zipball for pre-storage scans.
 */
export default function InstallCard({
  slug,
  installsTotal,
  latestVersion,
  githubUrl,
  download,
}: Props) {
  const [copied, setCopied] = useState(false)
  const command = `npx saferskills install ${slug} --to claude-code`
  const hasSnapshot = download != null
  const downloadUrl = hasSnapshot
    ? itemDownloadUrl(slug, download.scan_id)
    : latestVersion
      ? `${githubUrl}/archive/refs/tags/${latestVersion}.zip`
      : `${githubUrl}/archive/HEAD.zip`
  const zipMeta = hasSnapshot
    ? `${slug}.zip · ${fmtBytes(download.byte_size)} · via SaferSkills`
    : `${slug}${latestVersion ? `-${latestVersion}` : ''}.zip · via GitHub`

  return (
    <div className="side-card install-card">
      <h4>Install via SaferSkills</h4>
      <div className="sk-term">
        <div className="sk-term-chrome">
          <span className="mac-traffic">
            <span className="l-r" />
            <span className="l-y" />
            <span className="l-g" />
          </span>
          <button
            type="button"
            className="sk-term-copy"
            aria-label="Copy install command"
            onClick={() => {
              navigator.clipboard?.writeText(command)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
          >
            {copied ? '✓ Copied' : '⧉ Copy'}
          </button>
        </div>
        <div className="sk-term-body">
          <span>
            <span className="pr">$</span>npx saferskills install {slug}
          </span>
          <span className="arg">--to claude-code</span>
        </div>
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
        <span className="zip-meta">{zipMeta}</span>
      </div>
      <div className="install-count">
        <span className="ic-num">{installsTotal.toLocaleString()}</span>
        <span className="ic-lbl">installs via SaferSkills</span>
      </div>
    </div>
  )
}
