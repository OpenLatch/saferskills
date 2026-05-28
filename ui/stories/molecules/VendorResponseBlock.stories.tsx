import type { Story } from '@ladle/react'
import VendorResponseBlock from '../../components/molecules/VendorResponseBlock'

export const Default: Story = () => (
  <VendorResponseBlock
    bodyMarkdown={
      "Thanks for the audit. The curl|bash pattern flagged by SS-HOOKS-RCE-CURL-PIPE-01 is intentional — it's a self-update mechanism users explicitly opt into via a setup flag. We've added a confirmation prompt in the next minor release and updated the README to call this out."
    }
    author="anthropics"
    submittedAt="2026-05-26T12:34:00Z"
    version={2}
    respondHref="/items/anthropics--skills/respond"
  />
)

export const NoRespondCTA: Story = () => (
  <VendorResponseBlock
    bodyMarkdown="Acknowledged — patched in 1.4.2."
    author="acme-org"
    submittedAt="2026-05-25T09:00:00Z"
  />
)
