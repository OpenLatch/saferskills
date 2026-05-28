import CopyButton from '../atoms/CopyButton'

interface Props {
  /** The catalog slug — `<org>--<repo>`. */
  slug: string
  /** Override the default `npx saferskills install <slug>` command. */
  command?: string
  /** Optional label for the agent target the command will install into. */
  agentLabel?: string
  /** PostHog telemetry hook — fires on the copy button click. Parent attaches
   *  on the wrapping section via event delegation since CopyButton doesn't
   *  expose a click callback. */
  onCopy?: (commandType: 'npx' | 'web') => void
}

/**
 * Single-command install box rendered on /scans/<id> and /items/<slug>.
 * Vocabulary: `mockups/hifi/app-pages.css::.report-install`. Mono command, copy
 * button, optional agent-target hint.
 */
export default function InstallCommandBox({ slug, command, agentLabel, onCopy }: Props) {
  const finalCommand = command ?? `npx saferskills install ${slug}`

  function handleClick(e: React.MouseEvent<HTMLElement>) {
    if (!onCopy) return
    const target = e.target as HTMLElement
    if (target.closest('button')) onCopy('npx')
  }

  return (
    <section className="install-command-box" aria-label="Install command" onClick={handleClick}>
      <header className="install-command-box-head">
        <span className="eyebrow eyebrow-rule">INSTALL · NPX</span>
        {agentLabel ? <span className="install-command-box-agent">{agentLabel}</span> : null}
      </header>
      <pre className="install-command-box-pre">
        <code>{finalCommand}</code>
        <CopyButton value={finalCommand} label="Copy" />
      </pre>
      <p className="install-command-box-hint">
        Runs the SaferSkills installer — checks the signed report, prompts before installing.
      </p>
    </section>
  )
}
