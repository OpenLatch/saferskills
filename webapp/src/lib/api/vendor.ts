/**
 * Vendor right-of-reply client helpers.
 *
 * These hit **same-origin Astro endpoints** under `/items/<slug>/respond/*`
 * (not the FastAPI backend directly). The Astro endpoints own the
 * `ss_vendor_session` HttpOnly cookie (set on redeem, read on submit) and
 * proxy to the backend. Verified state is therefore never readable by browser
 * JS — these helpers only ever see opaque success/error JSON.
 *
 * No `fetchVerificationState` here: the `/items/<slug>/respond` SSR page reads
 * the cookie server-side (forwarding it to the backend `/vendor/session`) and
 * branches before any JS runs.
 */

export interface VerifyStartResult {
  token: string
  expires_at: string
  file_path: string
}

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `request failed (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string; error?: string }
      detail = data.detail ?? data.error ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export function issueVerifyToken(slug: string): Promise<VerifyStartResult> {
  return postJson<VerifyStartResult>(`/items/${slug}/respond/issue`)
}

export function redeemVerifyToken(
  slug: string,
  payload: { token: string; github_user: string }
): Promise<{ ok: true }> {
  return postJson<{ ok: true }>(`/items/${slug}/respond/redeem`, payload)
}

export function submitVendorResponse(
  slug: string,
  payload: { body_markdown: string; trigger_rescan: boolean }
): Promise<{ ok: true; rescan_triggered: boolean }> {
  return postJson<{ ok: true; rescan_triggered: boolean }>(`/items/${slug}/respond/submit`, payload)
}
