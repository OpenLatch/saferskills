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
 * Wordmark + GhStar + scan CTA are rendered as Astro slots in webapp pages
 * so this island stays framework-agnostic. The CSS lives in
 * `webapp/src/styles/components.css::.nav`.
 */
export default function NavBar({
  links = DEFAULT_LINKS,
  ghCount = 0,
  scanHref = '/scan',
}: Props) {
  const [scrolled, setScrolled] = useState(false)

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

  const pathname = typeof window !== 'undefined' ? window.location.pathname : '/'

  return (
    <nav className={`nav ${scrolled ? 'scrolled' : ''}`.trim()} aria-label="Main navigation">
      <div className="nav-inner">
        <span className="nav-corner tl" aria-hidden="true" />
        <span className="nav-corner tr" aria-hidden="true" />
        <span className="nav-corner bl" aria-hidden="true" />
        <span className="nav-corner br" aria-hidden="true" />

        <a href="/" className="brand" aria-label="SaferSkills home">
          <span className="mk" aria-hidden="true" />
          SaferSkills
        </a>

        <ul className="nav-links">
          {links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                aria-current={pathname === link.href ? 'page' : undefined}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="nav-right btn-pair">
          {ghCount > 0 && <GhStar count={ghCount} />}
          <a href={scanHref} className="btn primary sm">
            Scan a repo
          </a>
        </div>
      </div>
    </nav>
  )
}
