import type { Story } from '@ladle/react'

// Footer is an Astro component. The Ladle shell renders a static React
// approximation of the dark-slate footer chrome for visual review.

export const Default: Story = () => (
  <footer
    style={{
      background: '#0F172A',
      color: '#F8FAFC',
      padding: '80px 32px 28px',
      fontFamily: 'system-ui, sans-serif',
      borderTop: '1px solid #0F172A',
    }}
  >
    <div style={{ maxWidth: 1280, margin: '0 auto' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr',
          gap: 48,
        }}
      >
        <div>
          <span style={{ fontSize: 44, fontWeight: 600, fontFamily: 'Onest', letterSpacing: '-0.04em' }}>
            SaferSkills
          </span>
          <p style={{ color: '#CBD5E1', maxWidth: 360, marginTop: 14, fontSize: 15 }}>
            Every AI capability, independently audited. Public, open-source trust scoring across every agent platform.
          </p>
          <p style={{ color: '#64748B', marginTop: 20, fontFamily: 'monospace', fontSize: 11 }}>
            Stewarded by OpenLatch
          </p>
        </div>
        {['SCORES', 'AGENTS', 'DOCS', 'PROJECT'].map((label) => (
          <div key={label}>
            <h6 style={{ fontFamily: 'monospace', fontSize: 11, letterSpacing: '0.3em', color: '#F97316', margin: '0 0 18px' }}>
              {label}
            </h6>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {['Item one', 'Item two', 'Item three'].map((l) => (
                <li key={l} style={{ padding: '5px 0', fontSize: 14, opacity: 0.86 }}>
                  {l}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  </footer>
)
