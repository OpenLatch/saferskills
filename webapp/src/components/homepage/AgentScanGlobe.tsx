import { useEffect, useRef } from 'react'

/**
 * Agent-Scan band rotating wireframe globe (I-5.7 D-5.7-11 — founder kept the
 * canvas). Port of the v3 mockup's `as-globe` drawing code with containment:
 *
 *   - IntersectionObserver: the rAF loop runs ONLY while the canvas
 *     intersects the viewport (cancel on exit, resume on re-entry —
 *     `client:visible` only delays first hydration).
 *   - prefers-reduced-motion: exactly ONE static frame, no loop.
 *   - devicePixelRatio capped at 2; resize via a debounced ResizeObserver.
 *   - No per-frame allocations: the unit sphere + projection buffers are
 *     allocated once and mutated in place.
 *   - Purely decorative: aria-hidden, pointer-events: none (page CSS).
 *
 * Pre-approved fallback if the Lighthouse gate fails on this canvas: swap the
 * island for a static SVG frame (D-5.7-11) — a swap, not a redesign.
 */

const LAT = 10
const LON = 18
const STEP = 0.001
const RESIZE_DEBOUNCE_MS = 150

export default function AgentScanGlobe() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // Unit sphere lattice — allocated once.
    const px: number[] = []
    const py: number[] = []
    const pz: number[] = []
    for (let i = 0; i <= LAT; i++) {
      const theta = (Math.PI * i) / LAT
      for (let j = 0; j < LON; j++) {
        const phi = (2 * Math.PI * j) / LON
        px.push(Math.sin(theta) * Math.cos(phi))
        py.push(Math.cos(theta))
        pz.push(Math.sin(theta) * Math.sin(phi))
      }
    }
    const n = px.length
    // Projection buffers — mutated in place every frame (no per-frame allocs).
    const sx = new Float64Array(n)
    const sy = new Float64Array(n)
    const sd = new Float64Array(n)
    const ix = (i: number, j: number): number => i * LON + (((j % LON) + LON) % LON)

    // Diagonal rotation axis (in-plane, tilted) → tumbles like a rolling ball.
    let ax = 0.62
    let ay = 0.74
    let az = 0.26
    const al = Math.sqrt(ax * ax + ay * ay + az * az)
    ax /= al
    ay /= al
    az /= al

    let ang = 0
    let raf: number | null = null
    let running = false

    // Depth-faded stroke between two projected points. Alpha rides
    // ctx.globalAlpha (a number) — no per-edge rgba string allocation.
    function line(a: number, b: number): void {
      if (!ctx) return
      ctx.globalAlpha = 0.05 + 0.13 * (((sd[a] + sd[b]) / 2 + 1) / 2)
      ctx.beginPath()
      ctx.moveTo(sx[a], sy[a])
      ctx.lineTo(sx[b], sy[b])
      ctx.stroke()
    }

    function render(): void {
      if (!canvas || !ctx) return
      // Re-read DPR each render so zoom / monitor moves stay crisp (capped 2).
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const r = canvas.getBoundingClientRect()
      const tw = Math.max(1, Math.round(r.width * dpr))
      const th = Math.max(1, Math.round(r.height * dpr))
      if (canvas.width !== tw || canvas.height !== th) {
        canvas.width = tw
        canvas.height = th
      }
      const w = canvas.width
      const h = canvas.height
      ctx.clearRect(0, 0, w, h)
      const dark = document.documentElement.classList.contains('dark')
      const cx = w / 2
      const cy = h / 2
      const rad = Math.min(w, h) * 0.4
      const c = Math.cos(ang)
      const s = Math.sin(ang)
      const omc = 1 - c

      for (let k = 0; k < n; k++) {
        const x = px[k]
        const y = py[k]
        const z = pz[k]
        const dot = ax * x + ay * y + az * z
        const crx = ay * z - az * y
        const cry = az * x - ax * z
        const crz = ax * y - ay * x
        const rx = x * c + crx * s + ax * dot * omc
        const ry = y * c + cry * s + ay * dot * omc
        const rz = z * c + crz * s + az * dot * omc
        sx[k] = cx + rx * rad
        sy[k] = cy - ry * rad
        sd[k] = rz
      }

      ctx.lineWidth = dpr
      ctx.strokeStyle = dark ? 'rgb(226,232,240)' : 'rgb(15,23,42)'
      for (let i = 0; i <= LAT; i++) {
        for (let j = 0; j < LON; j++) {
          const a = ix(i, j)
          line(a, ix(i, j + 1))
          if (i < LAT) {
            line(a, ix(i + 1, j))
            line(a, ix(i + 1, j + 1))
          }
        }
      }
      ctx.fillStyle = dark ? 'rgb(45,212,191)' : 'rgb(13,148,136)'
      const nodeR = 1.5 * dpr
      for (let k = 0; k < n; k++) {
        ctx.globalAlpha = 0.3 + 0.45 * ((sd[k] + 1) / 2)
        ctx.beginPath()
        ctx.arc(sx[k], sy[k], nodeR, 0, 6.2832)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    function frame(): void {
      render()
      ang += STEP
      raf = requestAnimationFrame(frame)
    }
    function start(): void {
      if (running || reduce) return
      running = true
      raf = requestAnimationFrame(frame)
    }
    function stop(): void {
      running = false
      if (raf !== null) cancelAnimationFrame(raf)
      raf = null
    }

    render() // one synchronous frame (the only frame under reduced motion)

    let resizeTimer: ReturnType<typeof setTimeout> | null = null
    const ro = new ResizeObserver(() => {
      if (resizeTimer) clearTimeout(resizeTimer)
      resizeTimer = setTimeout(render, RESIZE_DEBOUNCE_MS)
    })
    ro.observe(canvas)

    let io: IntersectionObserver | null = null
    if (!reduce) {
      io = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) start()
          else stop()
        },
        { threshold: 0 }
      )
      io.observe(canvas)
    }

    return () => {
      stop()
      ro.disconnect()
      io?.disconnect()
      if (resizeTimer) clearTimeout(resizeTimer)
    }
  }, [])

  // Decorative-only canvas: tabIndex={-1} takes it out of the tab order so
  // aria-hidden is safe (Biome's noAriaHiddenOnFocusable treats a bare
  // <canvas> as potentially focusable); page CSS adds pointer-events: none.
  return <canvas ref={canvasRef} className="as-globe" aria-hidden="true" tabIndex={-1} />
}
