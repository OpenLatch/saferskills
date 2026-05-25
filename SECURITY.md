# Security

We take the security of SaferSkills itself seriously, and we treat reports as a partnership with the people who find issues.

## Scope

| In scope | Out of scope |
|---|---|
| Vulnerabilities in **SaferSkills code, infrastructure, CI pipeline, or release artifacts** (`services/api/`, `webapp/`, `ui/`, the CLI, the codegen scripts, the GitHub Actions workflows, the Fly.io deployment). | **Disputes about the verdict SaferSkills assigns to an item it scanned.** Those route through the vendor-appeal process — see `.github/ISSUE_TEMPLATE/04-vendor-appeal.yml` or `appeals@openlatch.ai`. |
| Supply-chain issues in our dependencies that affect SaferSkills users. | Vulnerabilities in items SaferSkills scans (those should be reported to the upstream maintainer). |

## Supported versions

| Version | Supported |
|---|---|
| `v0.x` (pre-launch, in development) | Latest commit on `main` only |
| Future `v1.x` | Latest minor + previous minor |

We do not currently backport fixes to pre-`v1.0` releases.

## Reporting a vulnerability

**Preferred**: GitHub Private Vulnerability Reporting at <https://github.com/OpenLatch/saferskills/security/advisories/new>.

**Alternative**: email `security@openlatch.ai` (PGP key fingerprint will be published with the first release).

Please include:
- The version (or git SHA) you tested
- A reproducible proof-of-concept (a minimal repo, a script, or a request sequence)
- The impact you observe
- Any mitigations or workarounds you've identified

## Response SLA

| Stage | Target |
|---|---|
| Acknowledgement | ≤ 72 hours |
| Initial triage + severity assessment | ≤ 7 days |
| Coordinated fix or update | ≤ 90 days (faster for Critical) |

Critical issues with active exploitation evidence get same-day response.

## Safe harbor

We will not pursue legal action under the Computer Fraud and Abuse Act (CFAA), the DMCA, or analogous laws against good-faith security researchers who:
- Make a good-faith effort to avoid privacy violations, service disruption, and data destruction
- Limit testing to your own accounts / scoped test fixtures
- Report the issue promptly via the channels above
- Do not publicly disclose until we've had a reasonable chance to respond (typically 90 days, sooner if we agree)

## Disclosure

Once a fix ships, we publish a GitHub Security Advisory with credit (or anonymous, if requested) and add the reporter to the Hall of Fame below.

## Hall of Fame

We thank the following researchers for responsible disclosures:

| Reporter | Issue | Year |
|---|---|---|
| _(empty — first responsible disclosure will appear here.)_ | | |
