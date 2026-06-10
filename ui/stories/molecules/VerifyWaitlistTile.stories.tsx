import type { Story } from '@ladle/react'
import VerifyWaitlistTile from '../../components/molecules/VerifyWaitlistTile'

export const Default: Story = () => (
  <div style={{ padding: 40, maxWidth: 760 }}>
    <VerifyWaitlistTile onSubmit={async (email) => alert(`waitlist: ${email ?? '(no email)'}`)} />
  </div>
)
