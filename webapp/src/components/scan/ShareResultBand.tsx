import RidgeFlow from '@ui/components/atoms/RidgeFlow'
import EmbedBadgeBox from '@ui/components/molecules/EmbedBadgeBox'

import type { ScoredTier } from '@/lib/tier'

/**
 * "Share this result" band — rendered on EVERY completed report (rich upload,
 * per-file upload tab, multi-capability repo). Public runs get the RidgeFlow
 * transition + dark blueprint band + README badge terminal; unlisted runs get the
 * light "badge locked until promote" variant (no ridge). The badge links to
 * /items/<slug> when a single capability slug is given, else to /scans/<scanId>.
 *
 * A plain React component (no Astro APIs) so it is reused both as an Astro island
 * (the repo path) and as a child of the React <UploadReport/> (per active file) —
 * one source of truth, no duplicated markup.
 */

interface Props {
  unlisted: boolean
  scanId: string
  score: number
  tier: ScoredTier | null
  /** Capability slug → badge links to /items/<slug>; omit → /scans/<scanId>. */
  slug?: string
  /** Sub-headline copy under the H3 (differs upload vs repo). */
  sub: string
  /** Foot descriptive sentence (differs upload vs repo). */
  foot: string
  scanIdShort: string
}

export default function ShareResultBand({
  unlisted,
  scanId,
  score,
  tier,
  slug,
  sub,
  foot,
  scanIdShort,
}: Props) {
  if (unlisted) {
    return (
      <section className="badge-band" data-screen-label="Private status + metadata">
        <div className="container">
          <div className="badge-wrap">
            <div className="bw-l">
              <span className="sb-eyebrow">Private link</span>
              <h3>This scan is unlisted</h3>
              <p>
                It is reachable only by its secret link — not indexed, not in the catalog. Promote
                it to public to make it shareable and badge-embeddable.
              </p>
            </div>
            <div className="bw-r">
              <div className="badge-locked">
                <span className="bl-lock" aria-hidden="true">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <rect x="4" y="11" width="16" height="10" />
                    <path d="M7.5 11 V7.5 a4.5 4.5 0 0 1 9 0 V11" />
                  </svg>
                </span>
                <p>
                  A public README badge becomes available once you{' '}
                  <b>promote this scan to public</b>. While unlisted, the result stays reachable
                  only by its secret link.
                </p>
              </div>
              <div className="bw-foot">
                {foot} &nbsp;·&nbsp; {scanIdShort}
              </div>
            </div>
          </div>
        </div>
      </section>
    )
  }

  return (
    <>
      <RidgeFlow label="— EMBED · BADGE —" className="ridge-flow--share" />
      <section className="badge-band badge-band--share" data-screen-label="README badge embed">
        <div className="container">
          <div className="badge-wrap">
            <div className="bw-l">
              <span className="sb-eyebrow">Share this result</span>
              <h3>Embed the badge in your README</h3>
              <p>{sub}</p>
            </div>
            <div className="bw-r">
              <EmbedBadgeBox scanId={scanId} score={score} tier={tier} slug={slug} />
              <div className="bw-foot">
                {foot} &nbsp;·&nbsp; {scanIdShort}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
