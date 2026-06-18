import type { Story } from '@ladle/react'
import SlackHexButton from '../../components/atoms/SlackHexButton'

export const Default: Story = () => <SlackHexButton />

export const InCluster: Story = () => (
  <div className="nav-right btn-pair">
    <SlackHexButton />
    <a className="gh-star">
      <span className="gh-l">★ Star</span>
      <span className="gh-r">27.1k</span>
    </a>
    <a href="/scan" className="btn primary sm">
      Run a scan
    </a>
  </div>
)
