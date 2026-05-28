import type { Story } from '@ladle/react'
import ScanStageCard from '../../components/molecules/ScanStageCard'

export const Pending: Story = () => (
  <ScanStageCard index="01" name="Fetch" description="Resolve repo + download tarball." status="pending" detectorsTotal={4} elapsedLabel="~2s" />
)

export const Running: Story = () => (
  <ScanStageCard index="02" name="Security" description="Prompt-injection + RCE + secret-exfil rules." status="running" detectorsDone={2} detectorsTotal={6} elapsedLabel="5.9s" />
)

export const Completed: Story = () => (
  <ScanStageCard index="01" name="Fetch" description="Resolve repo + download tarball." status="completed" detectorsDone={4} detectorsTotal={4} elapsedLabel="2.4s" />
)

export const Failed: Story = () => (
  <ScanStageCard index="01" name="Fetch" description="Repository not found." status="failed" detectorsTotal={4} elapsedLabel="0.4s" />
)
