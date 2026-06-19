import type { Story } from '@ladle/react'
import ActionCard from '../../components/molecules/ActionCard'

/**
 * ActionCard — `.p1-card` vocabulary.
 * Card head (ink machine-bar with seq + kicker + pulse), body slot for a
 * rich input + chips/progress, and a foot strip with CTA + meta.
 */

const FindInput = () => (
  <>
    <div className="p1-input">
      <span className="p1-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="7"></circle>
          <path d="m20 20-3.5-3.5"></path>
        </svg>
      </span>
      <label className="p1-field">
        <span className="caret" aria-hidden="true"></span>
        <input type="text" placeholder="ripgrep, supabase, linear..." aria-label="Search catalog" />
      </label>
      <button type="button" className="p1-enter" aria-label="Submit">
        <span className="key">↵</span>
      </button>
    </div>
    <div className="p1-tabs">
      <span className="lbl">Popular</span>
      <button type="button" className="p1-chip">
        <span className="kbd">Tab</span>
        <span className="nm">claude-pdf</span>
        <span className="sc green">95</span>
      </button>
      <button type="button" className="p1-chip">
        <span className="kbd">Tab</span>
        <span className="nm">github-mcp</span>
        <span className="sc green">87</span>
      </button>
    </div>
  </>
)

const AuditInput = () => (
  <>
    <div className="p1-input">
      <span className="p1-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 1 0-7.07-7.07l-1.5 1.5" />
          <path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 1 0 7.07 7.07l1.5-1.5" />
        </svg>
      </span>
      <label className="p1-field">
        <span className="caret" aria-hidden="true"></span>
        <input type="text" placeholder="github.com/anthropic/claude-mcp" aria-label="GitHub URL" />
      </label>
      <button type="button" className="p1-enter" aria-label="Submit">
        <span className="key">↵</span>
      </button>
    </div>
    <div className="p1-progress">
      <div className="row"><span>Audit pipeline</span><span><b>3</b> / 4 stages</span></div>
      <div className="bar"></div>
      <div className="steps">
        <span className="ok">Fetch</span>
        <span className="ok">Lint</span>
        <span className="cur">Score</span>
        <span className="pen">Sign</span>
      </div>
    </div>
  </>
)

export const Find: Story = () => (
  <ActionCard
    index="01"
    kicker="Find"
    liveLabel="Indexing"
    title="Search the catalog."
    lede="12,847 skills, MCPs, and plugins indexed from 12+ registries. One search instead of twelve."
    variant="find"
    foot={{
      cta: { label: 'Browse catalog →', href: '/catalog' },
      meta: <><b>12,847</b> indexed · <b>12</b> registries</>,
    }}
  >
    <FindInput />
  </ActionCard>
)

export const Audit: Story = () => (
  <ActionCard
    index="02"
    kicker="Audit"
    liveLabel="Running"
    title="Scan a new skill."
    lede="Paste a public GitHub URL. We return a full security report in ~30 seconds. Free. No account."
    variant="audit"
    foot={{
      cta: { label: 'Scan a skill →', href: '/scan' },
      meta: <>avg <b>28s</b> · free · no account</>,
    }}
  >
    <AuditInput />
  </ActionCard>
)

export const Grid: Story = () => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: 1180 }}>
    <ActionCard
      index="01"
      kicker="Find"
      liveLabel="Indexing"
      title="Search the catalog."
      lede="12,847 skills indexed."
      variant="find"
      foot={{ cta: { label: 'Browse →', href: '/catalog' }, meta: <><b>12,847</b> indexed</> }}
    >
      <FindInput />
    </ActionCard>
    <ActionCard
      index="02"
      kicker="Audit"
      liveLabel="Running"
      title="Scan a new skill."
      lede="Paste a GitHub URL."
      variant="audit"
      foot={{ cta: { label: 'Scan →', href: '/scan' }, meta: <>avg <b>28s</b></> }}
    >
      <AuditInput />
    </ActionCard>
  </div>
)
