import { useEffect, useRef } from 'react'

interface Props {
  /** Grid spacing in CSS px between crosses. */
  spacing?: number
  /** Cross arm half-length in CSS px. */
  arm?: number
  /** Cross stroke width in CSS px. */
  stroke?: number
  /** Alpha applied to `--color-ink` when composited onto `--color-paper` to derive the cross color. */
  strokeAlpha?: number
  /** Radius (px) around the cursor where crosses fade toward the background. */
  fadeRadius?: number
  /** Peak fade strength at cursor center (1 = fully dissolved into the background). */
  fadeStrength?: number
  /** Radius (px) within which crosses get pushed outward from the cursor. */
  pushRadius?: number
  /** Max displacement (px) at the cursor center. */
  pushMax?: number
  className?: string
}

/**
 * Interactive crosshair-grid backdrop — uniform `+` glyphs on `--color-paper`
 * with a soft fade-to-background void and a quadratic push around the cursor.
 *
 * Theme-aware: reads `--color-paper` + `--color-ink` from the document root,
 * re-reads when `<html>` class toggles (dark mode). Decorative only —
 * `pointer-events: none`, `aria-hidden`. Falls back to a fully static
 * single-frame render when `prefers-reduced-motion: reduce` is set OR the
 * primary input is coarse (`(pointer: coarse)` — phones / tablets): the RAF
 * loop is skipped, pointer listeners are inert, and the grid is redrawn only
 * on resize / theme flip.
 */
export default function CrosshairGrid({
  spacing = 50,
  arm = 3.5,
  stroke = 1,
  strokeAlpha = 0.16,
  fadeRadius = 110,
  fadeStrength = 0.85,
  pushRadius = 180,
  pushMax = 12,
  className = '',
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const canvasEl = canvasRef.current
    if (!canvasEl) return
    const ctx2d = canvasEl.getContext('2d')
    if (!ctx2d) return
    const canvas: HTMLCanvasElement = canvasEl
    const ctx: CanvasRenderingContext2D = ctx2d

    const CURSOR_LERP = 0.22

    let bgRGB = { r: 245, g: 247, b: 250 }
    let crossRGB = { r: 200, g: 205, b: 215 }
    let staticMode = false
    let dpr = Math.min(window.devicePixelRatio || 1, 2)
    let W = 0
    let H = 0
    let cells: Array<{ x: number; y: number }> = []
    let targetX = -9999
    let targetY = -9999
    let cx = -9999
    let cy = -9999
    let cursorActive = false
    let rafId = 0

    function readTokenRgb(varName: string): { r: number; g: number; b: number } {
      const probe = document.createElement('div')
      probe.style.color = `var(${varName})`
      probe.style.position = 'absolute'
      probe.style.visibility = 'hidden'
      probe.style.pointerEvents = 'none'
      document.body.appendChild(probe)
      const computed = getComputedStyle(probe).color
      document.body.removeChild(probe)
      const m = computed.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (!m) return { r: 0, g: 0, b: 0 }
      return {
        r: parseInt(m[1] ?? '0', 10),
        g: parseInt(m[2] ?? '0', 10),
        b: parseInt(m[3] ?? '0', 10),
      }
    }

    function readPalette() {
      const paper = readTokenRgb('--color-paper')
      const ink = readTokenRgb('--color-ink')
      bgRGB = paper
      crossRGB = {
        r: Math.round(ink.r * strokeAlpha + paper.r * (1 - strokeAlpha)),
        g: Math.round(ink.g * strokeAlpha + paper.g * (1 - strokeAlpha)),
        b: Math.round(ink.b * strokeAlpha + paper.b * (1 - strokeAlpha)),
      }
      requestDraw()
    }

    function buildGrid() {
      cells = []
      const offsetX = (W % spacing) / 2 + spacing / 2
      const offsetY = (H % spacing) / 2 + spacing / 2
      for (let y = offsetY; y < H; y += spacing) {
        for (let x = offsetX; x < W; x += spacing) {
          cells.push({ x, y })
        }
      }
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      const rect = canvas.getBoundingClientRect()
      W = Math.floor(rect.width)
      H = Math.floor(rect.height)
      if (W === 0 || H === 0) return
      canvas.width = Math.floor(W * dpr)
      canvas.height = Math.floor(H * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      buildGrid()
      requestDraw()
    }

    function requestDraw() {
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(frame)
    }

    function frame() {
      if (staticMode) {
        cursorActive = false
      } else if (cursorActive) {
        cx += (targetX - cx) * CURSOR_LERP
        cy += (targetY - cy) * CURSOR_LERP
      }

      ctx.fillStyle = `rgb(${bgRGB.r},${bgRGB.g},${bgRGB.b})`
      ctx.fillRect(0, 0, W, H)

      const RFADE2 = fadeRadius * fadeRadius
      const RPUSH2 = pushRadius * pushRadius

      ctx.lineWidth = stroke
      ctx.lineCap = 'square'

      for (let i = 0; i < cells.length; i++) {
        const c = cells[i]!

        let fade = 0
        let drawX = c.x
        let drawY = c.y

        if (cursorActive) {
          const dx = c.x - cx
          const dy = c.y - cy
          const dist2 = dx * dx + dy * dy

          if (dist2 < RFADE2) {
            const n = 1 - Math.sqrt(dist2) / fadeRadius
            fade = n * n * (3 - 2 * n) * fadeStrength
          }

          if (dist2 < RPUSH2 && dist2 > 0.0001) {
            const dist = Math.sqrt(dist2)
            const t = 1 - dist / pushRadius
            const push = pushMax * t * t
            drawX = c.x + (dx / dist) * push
            drawY = c.y + (dy / dist) * push
          }
        }

        const r = Math.round(crossRGB.r + (bgRGB.r - crossRGB.r) * fade)
        const g = Math.round(crossRGB.g + (bgRGB.g - crossRGB.g) * fade)
        const b = Math.round(crossRGB.b + (bgRGB.b - crossRGB.b) * fade)
        ctx.strokeStyle = `rgb(${r},${g},${b})`

        const x = Math.round(drawX) + 0.5
        const y = Math.round(drawY) + 0.5
        ctx.beginPath()
        ctx.moveTo(x - arm, y)
        ctx.lineTo(x + arm, y)
        ctx.moveTo(x, y - arm)
        ctx.lineTo(x, y + arm)
        ctx.stroke()
      }

      if (!staticMode) {
        rafId = requestAnimationFrame(frame)
      }
    }

    function setCursor(x: number, y: number) {
      if (!cursorActive) {
        cx = x
        cy = y
        cursorActive = true
      }
      targetX = x
      targetY = y
    }

    function activateFromClient(clientX: number, clientY: number) {
      const rect = canvas.getBoundingClientRect()
      const inside =
        clientX >= rect.left &&
        clientX <= rect.right &&
        clientY >= rect.top &&
        clientY <= rect.bottom
      if (inside) {
        setCursor(clientX - rect.left, clientY - rect.top)
      } else {
        cursorActive = false
      }
    }

    function onPointerMove(e: PointerEvent) {
      activateFromClient(e.clientX, e.clientY)
    }

    function onTouchMove(e: TouchEvent) {
      const t = e.touches[0]
      if (!t) return
      activateFromClient(t.clientX, t.clientY)
    }

    function onPointerLeave() {
      cursorActive = false
    }

    let pointerListenersAttached = false
    function attachPointerListeners() {
      if (pointerListenersAttached) return
      window.addEventListener('pointermove', onPointerMove, { passive: true })
      window.addEventListener('pointerleave', onPointerLeave)
      window.addEventListener('touchmove', onTouchMove, { passive: true })
      pointerListenersAttached = true
    }
    function detachPointerListeners() {
      if (!pointerListenersAttached) return
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', onPointerLeave)
      window.removeEventListener('touchmove', onTouchMove)
      pointerListenersAttached = false
    }

    const reducedMotionMQ = window.matchMedia('(prefers-reduced-motion: reduce)')
    const coarsePointerMQ = window.matchMedia('(pointer: coarse)')
    staticMode = reducedMotionMQ.matches || coarsePointerMQ.matches

    const modeHandler = () => {
      const next = reducedMotionMQ.matches || coarsePointerMQ.matches
      if (next === staticMode) return
      staticMode = next
      if (staticMode) {
        cursorActive = false
        detachPointerListeners()
      } else {
        attachPointerListeners()
      }
      requestDraw()
    }
    reducedMotionMQ.addEventListener('change', modeHandler)
    coarsePointerMQ.addEventListener('change', modeHandler)

    const themeObserver = new MutationObserver(() => readPalette())
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })

    const hasResizeObserver = typeof ResizeObserver !== 'undefined'
    const ro = hasResizeObserver ? new ResizeObserver(() => resize()) : null
    if (ro) ro.observe(canvas)
    else window.addEventListener('resize', resize)

    readPalette()
    resize()
    requestDraw()

    if (!staticMode) attachPointerListeners()

    return () => {
      cancelAnimationFrame(rafId)
      detachPointerListeners()
      reducedMotionMQ.removeEventListener('change', modeHandler)
      coarsePointerMQ.removeEventListener('change', modeHandler)
      themeObserver.disconnect()
      if (ro) ro.disconnect()
      else window.removeEventListener('resize', resize)
    }
  }, [spacing, arm, stroke, strokeAlpha, fadeRadius, fadeStrength, pushRadius, pushMax])

  return (
    <canvas
      ref={canvasRef}
      className={`crosshair-grid ${className}`.trim()}
      aria-hidden="true"
    />
  )
}
