import { useEffect, useState } from 'react'

interface Props {
  base: string
  nouns: string[]
  cycleMs?: number
  fadeMs?: number
  pauseOnHover?: boolean
  respectsReducedMotion?: boolean
}

/**
 * Rotating-noun homepage hero headline (D-FE-32).
 *
 * Renders `{base} <mark>{nouns[i]}</mark>`. The mark gets a teal-tint
 * underline highlight + loud font weight.
 *
 * `prefers-reduced-motion: reduce` short-circuits to a static list of all
 * nouns separated by ` · ` — no animation, no rotation.
 */
export default function RotatingHeadline({
  base,
  nouns,
  cycleMs = 4000,
  fadeMs = 300,
  pauseOnHover = true,
  respectsReducedMotion = true,
}: Props) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [opacity, setOpacity] = useState(1)
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    if (!respectsReducedMotion || typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [respectsReducedMotion])

  useEffect(() => {
    if (reducedMotion || paused || nouns.length <= 1) return
    const interval = setInterval(() => {
      setOpacity(0)
      setTimeout(() => {
        setIndex((i) => (i + 1) % nouns.length)
        setOpacity(1)
      }, fadeMs)
    }, cycleMs)
    return () => clearInterval(interval)
  }, [reducedMotion, paused, nouns.length, cycleMs, fadeMs])

  if (reducedMotion) {
    return (
      <h1 className="h-display rotating-headline reduced">
        {base}{' '}
        <span className="mark">{nouns.join(' · ')}</span>
      </h1>
    )
  }

  return (
    <h1
      className="h-display rotating-headline"
      onMouseEnter={pauseOnHover ? () => setPaused(true) : undefined}
      onMouseLeave={pauseOnHover ? () => setPaused(false) : undefined}
    >
      {base}{' '}
      <span
        className="mark active"
        style={{ opacity, transition: `opacity ${fadeMs}ms ease` }}
      >{nouns[index]}</span>
    </h1>
  )
}
