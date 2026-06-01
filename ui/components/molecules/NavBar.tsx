import { useEffect, useState } from 'react'
import GhStar from '../atoms/GhStar'

interface NavLink {
  label: string
  href: string
}

interface Props {
  links?: NavLink[]
  ghCount?: number
  scanHref?: string
  /**
   * Current route path, passed from the Astro route (`Astro.url.pathname`) so
   * the active link is computed identically on the server and the client.
   * Reading `window.location` during render caused a hydration mismatch.
   */
  activePath?: string
}

const DEFAULT_LINKS: NavLink[] = [
  { label: 'Home', href: '/' },
  { label: 'Catalog', href: '/catalog' },
  { label: 'Scan', href: '/scan' },
  { label: 'Docs', href: '/docs' },
  { label: 'Methodology', href: '/methodology' },
]

/**
 * Site nav with the scrolled-pill morph (D-FE-08 + D-FE-NEW).
 *
 * Transparent + full-width when `scrollY < 24`, then constrains to
 * `max-width: 1100px`, gains `backdrop-filter: blur(12px)`, hairline border,
 * soft shadow, and 4 corner registration marks.
 *
 * Below 860px the horizontal nav (links + GhStar + scan CTA) no longer fits,
 * so it collapses to a hamburger button that opens a slide-down drawer holding
 * the same links + GhStar + CTA. The desktop row and the drawer share one
 * `links` source; CSS toggles which is visible per breakpoint.
 */
export default function NavBar({
  links = DEFAULT_LINKS,
  ghCount,
  scanHref = '/scan',
  activePath,
}: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    let raf = 0
    const update = () => {
      raf = 0
      setScrolled(window.scrollY > 24)
    }
    const onScroll = () => {
      if (!raf) raf = window.requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      if (raf) cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  // Close the mobile drawer on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const isActive = (href: string) =>
    activePath === href ? 'page' : undefined

  return (
    <nav className={`nav ${scrolled ? 'scrolled' : ''}`.trim()} aria-label="Main navigation">
      <div className="nav-inner">
        <span className="nav-corner tl" aria-hidden="true" />
        <span className="nav-corner tr" aria-hidden="true" />
        <span className="nav-corner bl" aria-hidden="true" />
        <span className="nav-corner br" aria-hidden="true" />

        <a href="/" className="brand" aria-label="SaferSkills home">
          <img
            className="mk"
            src="/logos/saferskills-logo-animated.svg"
            alt=""
            aria-hidden="true"
          />
          SaferSkills
        </a>

        <ul className="nav-links">
          {links.map((link) => (
            <li key={link.href}>
              <a href={link.href} aria-current={isActive(link.href)}>
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="nav-right btn-pair">
          {/* GhStar is ALWAYS present — never gate it on a count. A page that
              doesn't compute a count renders an empty chip that NavStars fills
              live. This is the single top bar; do not hand-roll another. */}
          <GhStar count={ghCount} />
          <a href={scanHref} className="btn primary sm">
            Scan a repo
          </a>
        </div>

        <button
          type="button"
          className="nav-toggle"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          aria-controls="nav-drawer"
          onClick={() => setOpen((v) => !v)}
        >
          <span className="nav-toggle-bars" data-open={open} aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </button>
      </div>

      <div
        id="nav-drawer"
        className="nav-drawer"
        data-open={open}
        hidden={!open}
      >
        <ul className="nav-drawer-links">
          {links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                aria-current={isActive(link.href)}
                onClick={() => setOpen(false)}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="nav-drawer-cta">
          <GhStar count={ghCount} />
          <a href={scanHref} className="btn primary sm" onClick={() => setOpen(false)}>
            Scan a repo
          </a>
        </div>
      </div>
    </nav>
  )
}
