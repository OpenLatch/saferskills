<!--
  SaferSkills — Privacy Policy (drafting source of truth)

  MAINTAINER NOTES — resolve before public launch (not part of the published text):
  1. Fill the controller block: exact OpenLatch legal name, legal form, registered
     address, and SIREN/RCS number. The body uses [OpenLatch legal name] / [address]
     / [SIREN] placeholders.
  2. Engineering precondition for this policy to be TRUE:
       - PostHog MUST run cookieless. Set `cookieless_mode: 'on_reject'` or
         `'always'` + persistence: 'memory' (or no persistence) and enable PostHog's
         "Cookieless server hash" so no cookies/localStorage IDs are written. The
         current `persistence: 'memory'` + `person_profiles: 'never'` config is
         already consistent with this; do not regress to cookie persistence without
         updating both this policy and the Cookie Policy + adding a consent banner.
       - Sentry MUST stay errors-only, `sendDefaultPii: false`, NO Session Replay.
       - Keep PostHog on the EU region host (eu.posthog.com / eu.i.posthog.com).
  3. Sign DPAs with each processor (Fly.io, PostHog, Sentry, and Resend when email
     ships) and keep the sub-processor list (§9) in sync.
  4. Document the Legitimate Interests Assessments referenced in §6 and §7 and keep
     them on file for CNIL.
  5. Re-review on EU "Digital Omnibus" adoption (expected H2 2026) — see §15.
  6. When auth + the newsletter + the /account/delete surface ship (Track E / W5),
     revise §4 (newsletter), §8 (rights — verification & self-serve deletion), and
     the retention table; the placeholders are marked "not yet active".
-->

# SaferSkills Privacy Policy

**Effective date:** 29 May 2026
**Last updated:** 29 May 2026
**Version:** 1.0

SaferSkills is a free, public, open-source service that independently scans publicly
available AI-agent artifacts — skills, MCP servers, hooks, rules, and plugins — from
the GitHub URLs people submit, and publishes a transparent, methodology-driven trust
report for each one.

This policy explains, in plain language, what personal data we process, why, on what
legal basis, who we share it with, how long we keep it, and the rights you have. We
have deliberately designed SaferSkills to collect **as little personal data as
possible**: there are no user accounts, no advertising, no third-party trackers, and
no cookies used for analytics or marketing.

---

## 1. At a glance

| What | Do we process it? | Why | Legal basis (GDPR) | How long |
|---|---|---|---|---|
| **GitHub URLs you submit** | Yes — and published | To scan the artifact and publish a public report | Legitimate interest (independent security transparency) | Indefinite (public record) |
| **Scan results & findings** | Yes — published | The core service | Legitimate interest | Indefinite (public record) |
| **Your IP address** | Yes — hashed immediately, raw IP never stored | Abuse prevention / rate-limiting only | Legitimate interest (security) | ~24 hours (rolling) |
| **Incidental personal data inside scanned public repositories** (e.g. an author name in code) | Only if present in the public repo | To produce the security report | Legitimate interest (network & information security) | See §7 |
| **Anonymous, cookieless usage analytics** | Yes — no identifiers, bucketed only | To understand aggregate usage and improve the service | Legitimate interest | ~90 days, then aggregated |
| **Error/diagnostic data** | Yes — personal data scrubbed | To detect and fix faults and abuse | Legitimate interest (security/operational integrity) | ~90 days |
| **Server logs** | Yes | Operations & security | Legitimate interest | ~30 days |
| **Newsletter email** | **Not yet active** (see §4) | Launch announcements (future) | Consent (when it launches) | Until you unsubscribe |
| **Your theme preference** | Stored on your device only | To remember light/dark mode | Strictly necessary (set by your action) | Until you clear it |

We do **not** sell or share your personal data for advertising, we do **not**
profile or fingerprint visitors, and we do **not** use marketing cookies.

---

## 2. Who we are (data controller)

The data controller responsible for the processing described here is:

> **[OpenLatch legal name]** ([legal form]), registered in France under
> SIREN/RCS **[SIREN]**, registered office **[registered address]**.
> SaferSkills is an OpenLatch project.

Because the controller is established in the European Union, **no Article 27 EU
representative is required**, and our lead supervisory authority is the French data
protection authority, the **CNIL** (Commission Nationale de l'Informatique et des
Libertés).

We have not appointed a statutory Data Protection Officer (we are not legally
required to). For any privacy matter, contact us at:

> **privacy@openlatch.ai**

---

## 3. The data we process and why

### 3.1 GitHub URLs you submit for scanning

When you submit a public GitHub URL to be scanned, we store that URL and use it to
fetch and analyse the referenced artifact. The submitted URL and the resulting scan
report become part of our **public catalog**. A submitted URL is not, by itself,
information about *you* — but we treat it transparently here because you provide it.

- **What we store:** the GitHub URL, the artifact metadata, and the scan output.
- **What we do not store:** we do **not** require, request, or retain your name,
  email, or account identity to run a scan. Scans are anonymous.
- **Legal basis:** legitimate interest in operating an independent, transparent,
  public security-scoring service (Art. 6(1)(f) GDPR). See §6.

### 3.2 Scan results and findings

Each scan produces a score, sub-scores, and a list of findings, each tied to a
documented detection rule (`rule_id`) and the rubric version that was active. To
protect the scanned author's content and any secrets it may contain, **evidence is
stored as a cryptographic hash (SHA-256) plus a file position — never the raw
content of the scanned artifact.** Scan results are public and retained
indefinitely as a transparency record (see §7 and §10).

### 3.3 Your IP address (abuse prevention only)

To prevent abuse and apply rate limits to scan submissions, we process the IP
address of incoming requests. **The raw IP address is hashed (SHA-256) on receipt
and is never written to our database or logs in raw form.** Only the hash, a coarse
counter, and a short time window are stored, and they expire on a rolling ~24-hour
basis.

- **Legal basis:** legitimate interest in the security and availability of the
  service (Art. 6(1)(f) GDPR).

### 3.4 Anonymous, cookieless usage analytics (PostHog)

We use **PostHog**, configured in **cookieless** mode and hosted in the **European
Union**, to understand how the service is used in aggregate. This deployment is
specifically designed to avoid identifying you:

- **No cookies and no persistent identifiers** are stored on your device for
  analytics. Because no information is stored on or read from your device for this
  purpose, **no cookie-consent banner is required** under the ePrivacy rules.
- **No user profiles** are created (`person_profiles` is disabled).
- Events are limited to a **fixed, closed list** of interaction names, and every
  numeric value is **bucketed** (for example a score is recorded as the range
  "70–89", not the exact figure). **Raw URLs, repository names, IP addresses and
  free-text input are never sent to analytics.**

- **Legal basis:** legitimate interest in measuring and improving the service
  (Art. 6(1)(f) GDPR). To the extent any analytics data is personal data at all, it
  is minimal, pseudonymous/aggregated, and you can object at any time (see §8).

### 3.5 Error and diagnostic monitoring (Sentry)

We use **Sentry** to capture application errors so we can fix faults and detect
abuse. Sentry is configured to **not send default personal data**
(`sendDefaultPii: false`), to **scrub** any breadcrumb that could contain scanned
content, and **Session Replay is not used**. Error reports may incidentally include
technical request metadata.

- **Legal basis:** legitimate interest in the security and operational integrity of
  the service (Art. 6(1)(f) GDPR).

### 3.6 Performance traces (OpenTelemetry)

Server-side traces and metrics (via OpenTelemetry, exported to infrastructure we
control) help us monitor performance. Trace attributes are limited to hashes, sizes,
and counts; **raw scanned content is never recorded**.

- **Legal basis:** legitimate interest in operating a reliable service.

### 3.7 Server logs

Our hosting and application layers keep standard operational logs (e.g. request
paths, status codes, timestamps). Logs are retained for ~30 days for security and
debugging.

- **Legal basis:** legitimate interest in security and operations.

### 3.8 Theme preference

If you switch between light and dark mode, that choice is stored **on your own
device** (`localStorage`, key `ss-theme`). It never leaves your browser and is not
sent to us. It is strictly necessary to honour a setting you chose, so no consent is
required.

---

## 4. Newsletter / launch list — not yet active

The website may display an email sign-up field for launch announcements. **At the
date of this policy, this feature is not active: no email address is collected,
transmitted to us, or stored.** When the newsletter does launch:

- it will operate strictly on an **opt-in consent** basis (Art. 6(1)(a) GDPR and the
  applicable ePrivacy electronic-marketing rules);
- emails will be sent through our processor **Resend**, from a sending domain shared
  with OpenLatch (`notifications.openlatch.ai`), with a reply-to at an
  `@openlatch.ai` mailbox;
- every message will contain a one-click unsubscribe, and you can withdraw consent
  at any time;
- this policy will be updated **before** any email is collected.

---

## 5. We do not knowingly process special-category or children's data

SaferSkills is a developer tool and is **not directed to children**. We do not
knowingly collect personal data from anyone under the age of **15** (the age of
digital consent in France). We do not intentionally process special categories of
data (Art. 9 GDPR). If incidental personal data of this kind appears inside a public
repository we scan, see §7.

---

## 6. Our use of "legitimate interests"

Most of our processing relies on the **legitimate interests** legal basis. For each
such activity we have carried out (and keep on file) a three-part balancing test —
purpose, necessity, and balancing against your rights and freedoms. In summary:

- **Purpose:** to provide a free, independent, transparent security-scoring service
  for publicly shared AI-agent artifacts, in the interest of the wider developer
  ecosystem. EU law expressly recognises **network and information security** as a
  legitimate interest.
- **Necessity:** each category of data above is the minimum needed for that purpose
  (e.g. hashing IPs rather than storing them; bucketing analytics; storing evidence
  hashes rather than raw content).
- **Balancing:** we minimise, pseudonymise, and never use this data for advertising
  or profiling, and you can object at any time (see §8).

You may request a summary of the relevant balancing assessment by emailing
privacy@openlatch.ai.

---

## 7. Scanning public repositories and the personal data they may contain

This section is specific to what SaferSkills does and we want to be clear about it.

We fetch and analyse **publicly available** code from GitHub. Public code can
contain personal data — for example an author's name, a username, or an email
address in commit metadata or in a file. **Data being public does not remove it from
the scope of data-protection law**, so we apply the following safeguards:

- **Lawful basis:** legitimate interest in independent security research and the
  network/information security of the AI-agent ecosystem (Art. 6(1)(f) GDPR), which
  carries a recognised public-interest weight.
- **Source and category (Article 14):** where we process personal data that we did
  not obtain from you directly (i.e. data inside a scanned repository), the source is
  the **public GitHub repository** identified in the report, and the categories are
  limited to whatever identifiers that public code happens to contain. We rely on the
  **Article 14(5) disproportionate-effort exemption** to provide this notice via this
  public policy and the public report, rather than contacting each individual.
- **Data minimisation:** our reports are about **artifacts and repositories, not
  people**. We reference the organisation/repository, and we do **not** publish
  authors' email addresses harvested from scanned code. Detection evidence is stored
  as **hashes and positions, never as raw payload**.
- **Right to object / right of reply:** every public verdict is appealable. Vendors
  and authors can submit a verified response through our vendor right-of-reply
  process, and individuals can object to, or request removal of, incidental personal
  data about them via privacy@openlatch.ai (see §8 and §10).

---

## 8. Your rights

Under the GDPR you have the right to:

- **access** the personal data we hold about you;
- **rectify** inaccurate data;
- **erase** data ("right to be forgotten"), subject to the public-record limits in
  §10;
- **restrict** processing;
- **data portability**;
- **object** to processing based on legitimate interests — including an absolute
  right to object to direct marketing;
- **withdraw consent** at any time where processing is based on consent (this will
  apply to the newsletter once it launches), without affecting prior processing.

To exercise any right, email **privacy@openlatch.ai**. We will respond within **one
month** (extendable by two further months for complex requests, with notice).
Because the service is anonymous, we may be unable to identify any data relating to a
purely anonymous visitor; where we cannot identify you we will say so. We may ask for
information reasonably necessary to verify a request.

You also have the right to **lodge a complaint with a supervisory authority** — for
us, the **CNIL** (www.cnil.fr) — or with the authority in your country of residence.

### Visitors in the United Kingdom

If you are in the UK, the UK GDPR and PECR give you equivalent rights. You can
complain to the UK **Information Commissioner's Office** (ico.org.uk). Note that the
UK Data (Use and Access) Act 2025 introduced some divergences from EU law; this does
not reduce the rights described above.

### Residents of US states with privacy laws

Depending on your state (e.g. California's CCPA/CPRA, Virginia, Colorado,
Connecticut, Texas and others), you may have rights to know, access, delete, and
correct your personal information, and to opt out of "sale" or "sharing" and
targeted advertising. **SaferSkills does not sell or share personal information and
does not use it for cross-context behavioural advertising.** We honour browser-based
**Global Privacy Control (GPC)** opt-out signals; because we run no advertising
trackers, there is in practice nothing to opt out of. To make a request or appeal a
decision, email privacy@openlatch.ai.

---

## 9. Who we share data with (processors / sub-processors)

We do not sell your data. We share the limited data described above only with the
service providers who help us run SaferSkills, each under a data-processing
agreement:

| Provider | Role | Data involved | Location / transfer safeguard |
|---|---|---|---|
| **Fly.io** | Application & database hosting | All service data at rest/in transit | Hosted in an EU region where available; transfers covered by SCCs / the provider's DPA |
| **PostHog** | Cookieless product analytics | Anonymous, bucketed event data only | **EU region (eu.posthog.com)** — kept in the EU |
| **Sentry** | Error monitoring | Diagnostic/error data with personal data scrubbed | Transfers to the US covered by the **EU-US Data Privacy Framework** and/or **Standard Contractual Clauses** |
| **GitHub** | Source of scanned public artifacts | Public repository content we fetch (not your personal data) | GitHub is the data *source*; we send it only the public resources we fetch |
| **Resend** (**not yet active** — newsletter only) | Transactional/announcement email | Email address (once the newsletter launches) | Transfers covered by the **EU-US DPF** and/or **SCCs** |

An up-to-date sub-processor list is available on request at privacy@openlatch.ai,
and we will update this table before adding a new sub-processor.

---

## 10. International data transfers

We prioritise keeping data in the EU (our hosting and analytics are EU-region where
available). Where a processor processes data outside the EEA — principally in the
United States (Sentry, and Resend once the newsletter launches) — we rely on the
**EU-US Data Privacy Framework** where the provider is certified, and/or on the
European Commission's **Standard Contractual Clauses** as a fallback, together with
supplementary measures. You can request a copy of the relevant safeguards at
privacy@openlatch.ai.

---

## 11. How long we keep data (retention)

| Data | Retention |
|---|---|
| Submitted GitHub URLs, scan results, findings (public catalog) | **Indefinite** — a public transparency record (see below) |
| Hashed IP / rate-limit counters | ~24 hours (rolling), then deleted |
| Cookieless analytics events | ~90 days, then retained only in aggregate |
| Error/diagnostic data (Sentry) | ~90 days |
| Server logs | ~30 days |
| Newsletter email (once active) | Until you unsubscribe, then deleted within 30 days |

**Public-record principle.** Scan results and the URLs that produced them are kept
indefinitely so that security findings remain verifiable and our methodology stays
auditable — transparency over erasure. We do **not** retroactively scrub the public
catalog except through the vendor right-of-reply / appeals process, or where we are
required to remove incidental personal data about an individual (see §7 and §8).

---

## 12. How we protect your data

We follow privacy-by-design and security-by-design principles, including: hashing IP
addresses on receipt; storing scan evidence as hashes rather than raw content;
scrubbing personal data from error reports; restricting outbound network access when
fetching artifacts; size-capping and validating every public input; and never
executing the code we scan (it is parsed as data only). No system is perfectly
secure, but we work to protect data against unauthorised access, loss, or misuse.

---

## 13. Automated decision-making

Scan scores are produced by **deterministic, documented detection rules**, not by
opaque profiling of individuals. The scoring relates to **artifacts**, not to people,
and does not produce legal or similarly significant effects on you within the meaning
of Article 22 GDPR. Every verdict is documented and appealable.

---

## 14. Links to other sites

Our reports link to GitHub and to third-party repositories and vendor sites. Those
destinations have their own privacy practices, which we do not control.

---

## 15. Changes to this policy

We may update this policy as the service evolves (for example when accounts or the
newsletter launch) or as the law changes. We are monitoring the EU **"Digital
Omnibus"** reform proposal (adopted as a Commission proposal in November 2025, not
yet law) and will update this policy if and when it takes effect. Material changes
will be reflected in the "Last updated" date above and, where appropriate, announced
on the site.

---

## 16. Contact

Questions, requests, or complaints about this policy or your personal data:

> **privacy@openlatch.ai**
> [OpenLatch legal name], [registered address], France

You may also contact or lodge a complaint with the **CNIL** (www.cnil.fr).
