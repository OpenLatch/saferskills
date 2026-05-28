import type { Story } from '@ladle/react'
import NavBar from '../../components/molecules/NavBar'

export const Default: Story = () => (
  <div style={{ minHeight: '120vh', background: 'var(--bg-page, #F8FAFC)' }}>
    <NavBar ghCount={26908} />
    <div style={{ padding: '120px 32px', maxWidth: 800, margin: '0 auto' }}>
      <p>Scroll down to see the nav-pill morph.</p>
    </div>
  </div>
)
