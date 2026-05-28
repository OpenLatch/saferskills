import type { Story } from '@ladle/react'
import ScanProgressBar from '../../components/molecules/ScanProgressBar'

export const Running: Story = () => (
  <ScanProgressBar completionPct={62} progressLabel="9 / 14 detectors complete" currentDetector="sec.net.outbound" currentDetectorElapsedMs={1100} />
)

export const Idle: Story = () => <ScanProgressBar completionPct={0} progressLabel="0 / 14 detectors" />

export const Done: Story = () => <ScanProgressBar completionPct={100} progressLabel="14 / 14 detectors complete" />

export const ReducedMotion: Story = () => (
  <ScanProgressBar completionPct={45} reducedMotion progressLabel="6 / 14 detectors complete" />
)
