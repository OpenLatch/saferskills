const SLACK_GLYPH = (
  <svg width="15" height="15" viewBox="0 0 122.8 122.8" aria-hidden="true">
    <path
      fill="currentColor"
      d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9zm6.5 0c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z"
    />
    <path
      fill="currentColor"
      d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2zm0 6.5c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58 0 52.2 0 45.1s5.8-12.9 12.9-12.9h32.3z"
    />
    <path
      fill="currentColor"
      d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97V45.2zm-6.5 0c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9v32.3z"
    />
    <path
      fill="currentColor"
      d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97h12.9zm0-6.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.6z"
    />
  </svg>
)

/**
 * Slack community CTA — an icon-only Slack glyph (`currentColor`, theme-aware
 * ink) with NO background by default. On hover a "half-cap twin" hex (the
 * GhStar pill's own shallow 16px caps) fills teal and the glyph flips to
 * contrast — the hex is a hover reveal. CSS lives in `ui/styles/components.css`
 * (`.slack-hex`); the half-cap masks live in `ui/styles/tokens.css`.
 *
 * Defaults to `/slack` — the stable redirect that 302s through the backend to
 * the live community-Slack invite. Placed left of the GhStar in the NavBar.
 */
export default function SlackHexButton({
  href = '/slack',
  className = '',
}: {
  href?: string
  className?: string
}) {
  return (
    <a
      className={`slack-hex ${className}`.trim()}
      href={href}
      aria-label="Join our Slack community"
    >
      {SLACK_GLYPH}
    </a>
  )
}
