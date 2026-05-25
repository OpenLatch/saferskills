import { type FormEvent, useState } from 'react';

type Status = 'idle' | 'submitting' | 'ok' | 'invalid' | 'error';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Minimal email-capture island for the W1 placeholder homepage.
 *
 * The W1 wire posts to the Resend audiences API directly from the browser.
 * The audience ID is exposed via `PUBLIC_RESEND_AUDIENCE_ID` (a public token —
 * never put a real secret behind a PUBLIC_ key). When the audience id is
 * unset (local dev), the submission resolves to a no-op with the "ok" UI so
 * the form is exercisable without external services.
 */
export default function EmailCaptureForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');

  const audienceId = import.meta.env.PUBLIC_RESEND_AUDIENCE_ID ?? '';

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setStatus('invalid');
      return;
    }
    setStatus('submitting');

    try {
      if (!audienceId) {
        // Dev mode — no-op success.
        await new Promise((resolve) => setTimeout(resolve, 300));
        setStatus('ok');
        return;
      }

      const response = await fetch(`https://api.resend.com/audiences/${audienceId}/contacts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, unsubscribed: false }),
      });

      if (response.ok) {
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
      <p className="mt-6 text-base" style={{ color: 'rgb(var(--score-green))' }}>
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
          border: 'var(--border-width) solid rgb(var(--border))',
          background: 'rgb(var(--background))',
          color: 'rgb(var(--foreground))',
          padding: '12px 14px',
          fontFamily: 'inherit',
          fontSize: 'var(--type-base)',
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
          background: 'rgb(var(--primary))',
          color: 'rgb(var(--primary-fg))',
          padding: '12px 24px',
          fontFamily: 'inherit',
          fontWeight: 600,
          fontSize: 'var(--type-base)',
          border: 0,
          borderRadius: 0,
          cursor: status === 'submitting' ? 'wait' : 'pointer',
          opacity: status === 'submitting' ? 0.6 : 1,
        }}
      >
        {status === 'submitting' ? 'Subscribing…' : 'Notify me'}
      </button>
      {status === 'invalid' && (
        <p className="text-sm w-full sm:w-auto" style={{ color: 'rgb(var(--score-red))' }}>
          Enter a real email.
        </p>
      )}
      {status === 'error' && (
        <p className="text-sm w-full sm:w-auto" style={{ color: 'rgb(var(--score-red))' }}>
          Something went wrong. Try again later or email us at hello@openlatch.ai.
        </p>
      )}
    </form>
  );
}
