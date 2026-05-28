import type { Story } from '@ladle/react'
import { useEffect } from 'react'
import Toast, { flashToast } from '../../components/atoms/Toast'

const Trigger = ({ message }: { message: string }) => {
  useEffect(() => {
    const t = setTimeout(() => flashToast(message), 300)
    return () => clearTimeout(t)
  }, [message])
  return (
    <div style={{ padding: 40, minHeight: 200 }}>
      <button type="button" onClick={() => flashToast(message)}>
        Trigger toast
      </button>
      <Toast />
    </div>
  )
}

export const Copied: Story = () => <Trigger message="Copied to clipboard" />
export const Subscribed: Story = () => <Trigger message="Subscribed — see you at launch" />
export const LongMessage: Story = () => <Trigger message="Scan submitted · queued at position 12 (estimated 28s)" />
