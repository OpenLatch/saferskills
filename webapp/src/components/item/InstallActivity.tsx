import Eyebrow from '@ui/components/atoms/Eyebrow'

import type { InstallActivity as InstallActivityData } from '@/lib/api/items'

interface Props {
  activity: InstallActivityData
}

/**
 * Item-detail column 3 — anonymized install counts + agent distribution.
 *
 * Anonymized counts ONLY — never company-level data (company intelligence is
 * OpenLatch's private B2B surface, never public). At I-03 ship these are
 * deterministic placeholders from the catalog item's popularity_score; I-05
 * (Install CLI) wires real install telemetry.
 */
export default function InstallActivity({ activity }: Props) {
  return (
    <div className="install-activity-card">
      <Eyebrow withRule>INSTALL ACTIVITY</Eyebrow>
      <div className="ia-row">
        <span className="ia-label">This week</span>
        <span className="ia-num">{activity.this_week.toLocaleString()}</span>
      </div>
      <div className="ia-row">
        <span className="ia-label">This month</span>
        <span className="ia-num">{activity.this_month.toLocaleString()}</span>
      </div>
      <div className="ia-row">
        <span className="ia-label">All time</span>
        <span className="ia-num">{activity.all_time.toLocaleString()}</span>
      </div>
      <div className="ia-divider" />
      <div className="ia-agents">
        <span className="ia-agents-label">By agent</span>
        <div className="ia-agent-bar" role="img" aria-label="Install distribution by agent">
          {activity.agent_distribution.map((d) => (
            <span
              key={d.agent}
              className="ia-agent-seg"
              style={{ width: `${d.percentage}%` }}
              title={`${d.agent} ${d.percentage}%`}
            />
          ))}
        </div>
        <ul className="ia-agent-legend">
          {activity.agent_distribution.map((d) => (
            <li key={d.agent}>
              <span className="ia-agent-name">{d.agent}</span>
              <span className="ia-agent-pct">{d.percentage}%</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="ia-note">Anonymized counts. Real install telemetry lands with the CLI.</p>
    </div>
  )
}
