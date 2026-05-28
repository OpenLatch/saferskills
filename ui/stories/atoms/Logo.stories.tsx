import type { Story } from '@ladle/react'

// Logo is an Astro component. Ladle hosts a React shell that loads the SVG
// the same way the Astro template does — through the public asset path.

const renderImg = (src: string, size: number) => (
  <img src={src} alt="" aria-hidden="true" width={size} height={size} />
)

export const Default: Story = () => renderImg('/logos/saferskills-logo.svg', 80)
export const Ink: Story = () => renderImg('/logos/saferskills-logo-bw.svg', 80)
export const Light: Story = () => renderImg('/logos/saferskills-light-logo.svg', 80)
export const SmallCluster: Story = () => (
  <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
    {[16, 24, 40, 56, 80].map((px) => renderImg('/logos/saferskills-logo.svg', px))}
  </div>
)
