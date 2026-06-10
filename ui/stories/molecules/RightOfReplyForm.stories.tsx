import type { Story } from '@ladle/react'
import RightOfReplyForm from '../../components/molecules/RightOfReplyForm'

export const Empty: Story = () => (
  <div style={{ padding: 40 }}>
    <RightOfReplyForm onSubmit={async (body) => alert(`reply: ${body}`)} />
  </div>
)

export const WithExistingReply: Story = () => (
  <div style={{ padding: 40, maxWidth: 620 }}>
    <RightOfReplyForm
      onSubmit={async () => {}}
      existingReply="We strip embedded tool-description directives at registration as of v2.3 — re-scan pending."
    />
  </div>
)
