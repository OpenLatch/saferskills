import Button from '@ui/components/atoms/Button'
import CopyButton from '@ui/components/atoms/CopyButton'
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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div className="verify-challenge">
      <ol className="verify-steps">
        <li className={step === 'request' ? 'active' : 'done'}>
          <Eyebrow>STEP 1 · REQUEST A TOKEN</Eyebrow>
          <p>
            Confirm you control{' '}
            <code>
              github.com/{githubOrg}/{githubRepo}
            </code>{' '}
            by committing a one-time token to its default branch.
          </p>
          {step === 'request' && (
            <Button variant="primary" onClick={requestToken} disabled={busy}>
              {busy ? 'Issuing…' : 'Issue verification token'}
            </Button>
          )}
        </li>

        {step === 'commit' && token && (
          <>
            <li className="active">
              <Eyebrow>STEP 2 · COMMIT THE TOKEN</Eyebrow>
              <p>
                Create <code>{filePath}</code> in your repo root, paste the token below, then commit
                and push to the default branch.
              </p>
              <div className="verify-token">
                <code>{token}</code>
                <CopyButton value={token} label="Copy token" />
              </div>
            </li>

            <li className="active">
              <Eyebrow>STEP 3 · VERIFY</Eyebrow>
              <label className="verify-user-label">
                Your GitHub username
                <input
                  type="text"
                  className="form-input"
                  value={githubUser}
                  onChange={(e) => setGithubUser(e.currentTarget.value)}
                  placeholder="octocat"
                  autoComplete="off"
                />
              </label>
              <Button
                variant="primary"
                onClick={redeem}
                disabled={busy || githubUser.trim().length === 0}
              >
                {busy ? 'Verifying…' : "I've committed it — verify me"}
              </Button>
            </li>
          </>
        )}
      </ol>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
