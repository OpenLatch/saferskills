import Button from '@ui/components/atoms/Button'
import Eyebrow from '@ui/components/atoms/Eyebrow'
import { useState } from 'react'

import { issueVerifyToken, redeemVerifyToken } from '@/lib/api/vendor'

interface Props {
  slug: string
  githubOrg: string
  githubRepo: string
}

type Step = 'request' | 'commit'

/**
 * "Verify yourself" sub-flow for the vendor right-of-reply. No token ever in a
 * URL: the raw token is shown once on-screen for the vendor to commit to
 * `.saferskills/verify.txt`; redemption sets the HttpOnly session cookie
 * (server-side) and we reload so the SSR page renders the verified branch.
 */
export default function VerifyChallenge({ slug, githubOrg, githubRepo }: Props) {
  const [step, setStep] = useState<Step>('request')
  const [token, setToken] = useState<string | null>(null)
  const [filePath, setFilePath] = useState('.saferskills/verify.txt')
  const [githubUser, setGithubUser] = useState('')
  const [userTouched, setUserTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  function copyToken() {
    if (!token) return
    navigator.clipboard?.writeText(token)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  async function requestToken() {
    setBusy(true)
    setError(null)
    try {
      const result = await issueVerifyToken(slug)
      setToken(result.token)
      setFilePath(result.file_path)
      setStep('commit')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not issue a token. Try again.')
    } finally {
      setBusy(false)
    }
  }

  async function redeem() {
    if (!token) return
    setBusy(true)
    setError(null)
    try {
      await redeemVerifyToken(slug, { token, github_user: githubUser.trim() })
      // Cookie is set server-side — reload so the SSR page renders verified.
      window.location.assign(`/items/${slug}/respond`)
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'Verification failed. Confirm the file is committed to the default branch.'
      )
    } finally {
      setBusy(false)
    }
  }

  // Phase → per-step rail state. Step 1 is active until a token is issued, then
  // collapses to ✓ done; steps 2 + 3 are the live (active) pair once issued, and
  // dimmed/disabled "future" steps before that — so the whole 3-step workflow is
  // always visible as a rail.
  const issued = step === 'commit' && token !== null
  const s1 = issued ? 'done' : 'active'
  const s23 = issued ? 'active' : 'future'

  // Step 3 required-field validation: flag empty only once the field has been
  // touched (blurred), so the input doesn't start red. Clears live as they type.
  const userInvalid = userTouched && githubUser.trim().length === 0

  return (
    <div className="verify-challenge">
      <ol className="verify-rail">
        <li className={`rail-item ${s1}`}>
          <div className="rail-gutter">
            <span className="rail-node">{issued ? '✓' : '1'}</span>
            <span className="rail-conn" aria-hidden="true" />
          </div>
          <div className="rail-card">
            <Eyebrow>STEP 1 · REQUEST A TOKEN</Eyebrow>
            <p className="rail-text">
              Confirm you control{' '}
              <code>
                github.com/{githubOrg}/{githubRepo}
              </code>{' '}
              by committing a one-time token to its default branch.
            </p>
            {!issued && (
              <div className="rail-ctl">
                <Button variant="primary" onClick={requestToken} disabled={busy}>
                  {busy ? 'Issuing…' : 'Issue verification token'}
                </Button>
              </div>
            )}
            {!issued && error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <span className="rail-done-tag">✓ Token issued</span>
          </div>
        </li>

        <li className={`rail-item ${s23}`}>
          <div className="rail-gutter">
            <span className="rail-node">2</span>
            <span className="rail-conn" aria-hidden="true" />
          </div>
          <div className="rail-card">
            <Eyebrow>STEP 2 · COMMIT THE TOKEN</Eyebrow>
            {issued ? (
              <div className="rail-reveal">
                <p className="rail-text">
                  Create <code>{filePath}</code> in your repo root, paste the token below, then
                  commit and push to the default branch.
                </p>
                <div className="sk-term verify-token">
                  <div className="sk-term-chrome">
                    <span className="mac-traffic">
                      <span className="l-r" />
                      <span className="l-y" />
                      <span className="l-g" />
                    </span>
                    <span className="sk-term-title">{filePath}</span>
                    <button
                      type="button"
                      className="sk-term-copy"
                      aria-label="Copy token"
                      onClick={copyToken}
                    >
                      {copied ? '✓ Copied' : '⧉ Copy token'}
                    </button>
                  </div>
                  <div className="sk-term-body">
                    <span className="tok">{token}</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="rail-text muted">
                A one-time token appears here once you request it above.
              </p>
            )}
          </div>
        </li>

        <li className={`rail-item ${s23}`}>
          <div className="rail-gutter">
            <span className="rail-node">3</span>
          </div>
          <div className="rail-card">
            <Eyebrow>STEP 3 · VERIFY</Eyebrow>
            <p className="rail-text">
              Enter the GitHub username that pushed the commit — we re-read the default branch and
              match the token.
            </p>
            <div className="rail-ctl verify-submit-row">
              <label className="verify-user-label">
                Your GitHub username
                <input
                  type="text"
                  className={`form-input${userInvalid ? ' invalid' : ''}`}
                  value={githubUser}
                  onChange={(e) => setGithubUser(e.currentTarget.value)}
                  onBlur={() => setUserTouched(true)}
                  placeholder="octocat"
                  autoComplete="off"
                  disabled={!issued}
                  aria-invalid={userInvalid}
                  aria-describedby={userInvalid ? 'verify-user-error' : undefined}
                />
              </label>
              <Button
                variant="primary"
                onClick={redeem}
                className="verify-submit"
                disabled={!issued || busy || githubUser.trim().length === 0}
              >
                {busy ? 'Verifying…' : "I've committed it — verify me"}
              </Button>
            </div>
            {userInvalid && (
              <p className="verify-user-error" id="verify-user-error" role="alert">
                A GitHub username is required.
              </p>
            )}
            {issued && error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
          </div>
        </li>
      </ol>
    </div>
  )
}
