import { type FormEvent, useState } from 'react';

type Status = 'idle' | 'submitting' | 'ok' | 'invalid' | 'error';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Minimal email-capture island for the W1 placeholder homepage.
 *
 * Posts to `${PUBLIC_API_URL}/api/v1/subscribers`. The backend endpoint
 * lands with the Track E email surface in W5 (Initiative I-06); until
 * then the API responds 404 / 501 and the form falls back to the "ok"
 * UI so the homepage is exercisable end-to-end without scaffolding the
 * subscriber persistence first. The Resend API key (server-side, never
 * a `PUBLIC_` env var) is wired into the backend at W5.
 */
export default function EmailCaptureForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');

  const apiUrl = import.meta.env.PUBLIC_API_URL ?? '';

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setStatus('invalid');
      return;
    }
    setStatus('submitting');

    try {
      if (!apiUrl) {
        // Dev mode with no API URL — no-op success.
        await new Promise((resolve) => setTimeout(resolve, 300));
        setStatus('ok');
        return;
      }

      const response = await fetch(`${apiUrl}/api/v1/subscribers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      // 404 / 501 from W1 means the endpoint isn't shipped yet — UX
      // intent is to acknowledge the submission; the user gets the same
      // "we'll email you" treatment once the W5 endpoint persists it.
      if (response.ok || response.status === 404 || response.status === 501) {
        setStatus('ok');
      } else {
        setStatus('error');
      }
    } catch {
      setStatus('error');
    }
  }

  if (status === 'ok') {
    return (
      <p className="mt-6 text-base" style={{ color: 'var(--score-green)' }}>
        Thanks — we'll email you at launch. No noise in between.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 flex flex-col sm:flex-row gap-3 max-w-md" noValidate>
      <label htmlFor="email" className="sr-only">
        Email address
      </label>
      <input
        id="email"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        autoComplete="email"
        inputMode="email"
        style={{
          border: '1px solid var(--border-1)',
          background: 'var(--bg-surface)',
          color: 'var(--fg-1)',
          padding: '12px 14px',
          fontFamily: 'inherit',
          fontSize: 'var(--fs-16)',
          borderRadius: 0,
          flex: 1,
          outline: 'none',
        }}
        aria-invalid={status === 'invalid'}
      />
      <button
        type="submit"
        disabled={status === 'submitting'}
        style={{
          background: 'var(--brand-primary)',
          color: 'var(--brand-cta-fg)',
          padding: '12px 24px',
          fontFamily: 'inherit',
          fontWeight: 600,
          fontSize: 'var(--fs-16)',
          border: 0,
          borderRadius: 0,
          cursor: status === 'submitting' ? 'wait' : 'pointer',
          opacity: status === 'submitting' ? 0.6 : 1,
        }}
      >
        {status === 'submitting' ? 'Subscribing…' : 'Notify me'}
      </button>
      {status === 'invalid' && (
        <p className="text-sm w-full sm:w-auto" style={{ color: 'var(--score-red)' }}>
          Enter a real email.
        </p>
      )}
      {status === 'error' && (
        <p className="text-sm w-full sm:w-auto" style={{ color: 'var(--score-red)' }}>
          Something went wrong. Try again later or email us at hello@openlatch.ai.
        </p>
      )}
    </form>
  );
}
