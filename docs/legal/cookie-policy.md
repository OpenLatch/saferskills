<!--
  SaferSkills — Cookie Policy (drafting source of truth)

  MAINTAINER NOTES — keep this policy TRUE (not part of the published text):
  - This policy asserts SaferSkills sets NO cookies and uses NO non-essential
    storage. That is only correct while:
      * PostHog runs cookieless (no cookies, no localStorage IDs; EU host),
      * Sentry runs WITHOUT Session Replay (Replay uses sessionStorage),
      * no third-party embeds (YouTube/Vimeo/Calendly/Intercom/ad pixels) are added.
    Adding ANY of those introduces non-essential storage and REQUIRES:
      (a) updating this policy + the table below,
      (b) adding an EU consent banner with a first-layer "Reject all" of equal
          prominence to "Accept all", with no non-essential tags firing before
          consent, and honouring GPC.
  - The only client-side storage today is `localStorage['ss-theme']` (functional,
    first-party, on-device).
  - Keep the §"How we use storage" table in sync with the Privacy Policy §9/§3.
-->

# SaferSkills Cookie Policy

**Effective date:** 29 May 2026
**Last updated:** 29 May 2026
**Version:** 1.0

This Cookie Policy explains how SaferSkills uses cookies and similar device-storage
technologies. It supplements our [Privacy Policy](./privacy-policy.md).

The short version: **SaferSkills does not use cookies for analytics, advertising, or
tracking — and sets no tracking cookies at all.** We deliberately chose a
privacy-preserving, cookieless design.

---

## 1. What are cookies and similar technologies?

A **cookie** is a small text file a website stores on your device. "Similar
technologies" include browser storage such as `localStorage` and `sessionStorage`.
These technologies can be **strictly necessary / functional** (needed to provide
something you asked for, or to remember a preference you set) or **non-essential**
(for analytics, advertising, or tracking, which require your prior consent in the
EU/EEA).

---

## 2. Our approach: no tracking cookies

To keep the service privacy-friendly:

- **We do not use analytics cookies.** Our usage analytics (PostHog) run in
  **cookieless** mode on an EU server. They store **no cookie and no persistent
  identifier** on your device.
- **We do not use advertising or marketing cookies**, and we do not embed
  third-party ad or social trackers.
- **We do not fingerprint** your device.
- **Error monitoring** (Sentry) does not set cookies on our site and Session Replay
  is not used.

Because we set **no non-essential cookies or storage**, **no cookie-consent banner is
required** for the current site, and there is nothing for you to accept or reject.

---

## 3. The only storage we use

| Name | Type | Provider | Purpose | Where it lives | Duration | Category |
|---|---|---|---|---|---|---|
| `ss-theme` | `localStorage` (not a cookie) | SaferSkills (first-party) | Remembers your light/dark theme choice | **On your device only — never sent to us** | Until you clear it | Functional / strictly necessary (set by your own action) |

That is the complete list. We set **no cookies**, no analytics storage, and no
third-party storage.

---

## 4. Third-party services and storage

The services we rely on (described in our Privacy Policy §9) are configured **not**
to place tracking storage on your device when you use saferskills:

- **PostHog** — cookieless mode, EU region: **no cookies, no device identifier**.
- **Sentry** — error monitoring: **no cookies**; Session Replay is disabled.
- **GitHub** — we fetch public content from GitHub on the server side; this does not
  place GitHub storage on your device through our site. If you then visit GitHub
  directly, GitHub's own cookie practices apply.

If we ever add a feature that needs non-essential storage (for example, an embedded
video, a future logged-in experience, or analytics cookies), we will update this
policy **and** present a consent banner — with a "Reject all" option as prominent as
"Accept all" — **before** any such storage is set.

---

## 5. How to control storage in your browser

Even though we set no tracking cookies, you remain in full control:

- You can clear the `ss-theme` preference at any time by clearing your browser's
  site data for SaferSkills (your theme will simply reset to the default).
- All major browsers let you view, block, and delete cookies and site storage in
  their privacy/settings menus.
- We honour the **Global Privacy Control (GPC)** signal. Because we run no
  advertising or cross-site tracking, there is in practice nothing to opt out of, but
  the signal is respected.

---

## 6. Regional notes

- **EU/EEA (ePrivacy / French law):** consent is required only for non-essential
  cookies/storage. As we set none, no consent is collected. The single functional
  item (`ss-theme`) is set as a direct result of your own action and is exempt.
- **United Kingdom (PECR):** the same position applies; functional/preference storage
  set by your action does not require consent.
- **United States:** we do not "sell" or "share" personal information and use no
  advertising trackers; we honour GPC.

---

## 7. Changes to this policy

If our use of cookies or similar technologies changes, we will update this policy and
the "Last updated" date above, and — where the law requires it — ask for your consent
before setting any new non-essential storage.

---

## 8. Contact

Questions about this Cookie Policy:

> **privacy@openlatch.ai**

See also our [Privacy Policy](./privacy-policy.md).
