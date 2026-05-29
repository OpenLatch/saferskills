import Eyebrow from '@ui/components/atoms/Eyebrow'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { track } from '@/lib/analytics'
import type { ScanHistoryPoint } from '@/lib/api/items'

interface Props {
  points: ScanHistoryPoint[]
  thresholds?: number[]
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

const THRESHOLD_LABEL: Record<number, string> = {
  80: '80 · green',
  60: '60 · yellow',
  40: '40 · orange',
}

/**
 * 90-day score-history line chart (Recharts). Hydrated `client:visible` so the
 * ~50 KiB Recharts bundle defers until scroll-into-viewport. Tier-threshold
 * dashed lines at 80/60/40. Emits `item_detail_chart_explored` on hover/click.
 */
export default function ScoreHistoryChart({ points, thresholds = [80, 60, 40] }: Props) {
  const data = points.map((p) => ({
    date: new Date(p.scanned_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    score: p.aggregate_score,
  }))

  const first = points.at(0)?.aggregate_score ?? 0
  const last = points.at(-1)?.aggregate_score ?? 0
  const delta = last - first

  return (
    <div className="score-history-card">
      <Eyebrow withRule>SCORE · 90 DAYS</Eyebrow>
      {points.length > 0 && (
        <div className="score-history-meta">
          {first} → <b>{last}</b> {delta >= 0 ? '+' : ''}
          {delta}
        </div>
      )}
      {data.length === 0 ? (
        <p className="score-history-empty">No scans in the last 90 days yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={320} className="score-history-chart">
          <LineChart
            data={data}
            margin={{ top: 24, right: 56, bottom: 8, left: -8 }}
            onClick={() => track('item_detail_chart_explored', { interaction: 'click_point' })}
            onMouseMove={() => track('item_detail_chart_explored', { interaction: 'hover' })}
          >
            <CartesianGrid stroke="var(--color-line)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--fg-3)' }}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 40, 60, 80, 100]}
              axisLine={false}
              tickLine={false}
              tick={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--fg-3)' }}
            />
            {thresholds.map((t) => (
              <ReferenceLine
                key={t}
                y={t}
                stroke={
                  t >= 80
                    ? 'var(--score-green)'
                    : t >= 60
                      ? 'var(--score-yellow)'
                      : 'var(--score-orange)'
                }
                strokeDasharray="4 4"
                label={{
                  value: THRESHOLD_LABEL[t] ?? String(t),
                  position: 'right',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  fill: 'var(--fg-3)',
                }}
              />
            ))}
            <Line
              type="monotone"
              dataKey="score"
              stroke="var(--brand-primary)"
              strokeWidth={2}
              dot={{ fill: 'var(--brand-primary)', strokeWidth: 0, r: 4 }}
              activeDot={{ r: 6 }}
              isAnimationActive={!prefersReducedMotion()}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--color-paper)',
                border: '1px solid var(--color-ink)',
                borderRadius: 0,
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
              }}
              labelStyle={{ color: 'var(--color-ink)' }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
