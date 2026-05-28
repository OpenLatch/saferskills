import type { Story } from '@ladle/react'
import ScanInput from '../../components/molecules/ScanInput'

export const Default: Story = () => <ScanInput />

export const WithInitialValue: Story = () => <ScanInput initialValue="anthropics/skills" />

export const WithError: Story = () => (
  <ScanInput error="That repository is private or doesn't exist." />
)

export const Disabled: Story = () => <ScanInput disabled />
