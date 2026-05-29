import BandPill from '@ui/components/atoms/BandPill'
import DotStrip from '@ui/components/atoms/DotStrip'
import Eyebrow from '@ui/components/atoms/Eyebrow'
import ScoreNumber from '@ui/components/atoms/ScoreNumber'

import type { ScanReportDetail } from '@/lib/api/scans'
import { scoredTier, TIER_TO_STRIPE } from '@/lib/tier'

interface Props {
  scan: ScanReportDetail
  firstScanScore?: number | null
}

/**
 * Item-detail column 1 — the current aggregate score with a left tier stripe,
 * dot strip, band pill, and a delta-since-first-scan line. Mirrors the
 * scan-report hero score but in the narrow item-detail column layout.
 */
export default function ScoreCurrent({ scan, firstScanScore }: Props) {
  const tier = scoredTier(scan.tier) ?? 'red'
  const hasDelta = firstScanScore != null && firstScanScore !== scan.aggregate_score
  const delta = hasDelta ? scan.aggregate_score - (firstScanScore as number) : null

  return (
    <div className={`score-current stripe-l stripe-${TIER_TO_STRIPE[tier]}`}>
      <Eyebrow>CURRENT SCORE</Eyebrow>
      <ScoreNumber size="hero" value={scan.aggregate_score} />
      <DotStrip value={scan.aggregate_score} tier={tier} />
      <BandPill tier={tier} />
      {delta !== null && (
        <div className={`score-delta ${delta >= 0 ? 'up' : 'down'}`}>
          {delta >= 0 ? '↑' : '↓'} {delta >= 0 ? '+' : ''}
          {delta} since first scan ({firstScanScore} → {scan.aggregate_score})
        </div>
      )}
    </div>
  )
}
