import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'
import TurnstileGate from '../../../components/molecules/TurnstileGate'

// biome-ignore lint/suspicious/noExplicitAny: test shim for the Turnstile render opts
let lastOpts: any
let renderMock: ReturnType<typeof vi.fn>
let resetMock: ReturnType<typeof vi.fn>

describe('TurnstileGate', () => {
  beforeEach(() => {
    lastOpts = undefined
    renderMock = vi.fn((_el: HTMLElement, opts: { appearance?: string }) => {
      lastOpts = opts
      // Mirror real Cloudflare Turnstile: `appearance` accepts ONLY these
      // values (or undefined). Passing the widget *mode* ('managed') makes the
      // real `render()` throw — the bug that broke the whole gate on staging.
      // The mock must throw too, or the test gives false confidence.
      if (opts.appearance && !['always', 'execute', 'interaction-only'].includes(opts.appearance)) {
        throw new Error(`[Cloudflare Turnstile] Unknown appearance value: "${opts.appearance}"`)
      }
      return 'widget-1'
    })
    resetMock = vi.fn()
    ;(window as unknown as { turnstile: unknown }).turnstile = {
      render: renderMock,
      reset: resetMock,
      remove: vi.fn(),
    }
    // jsdom doesn't implement the native <dialog> modal methods.
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
      this.open = true
    })
    HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
      this.open = false
    })
  })

  afterEach(() => {
    // biome-ignore lint/performance/noDelete: clean module-level global between tests
    delete (window as unknown as { turnstile?: unknown }).turnstile
    vi.restoreAllMocks()
  })

  it('renders the heading + eyebrow + Cancel, and renders the widget when open', async () => {
    render(<TurnstileGate open siteKey="1x00AA" onVerified={() => {}} onCancel={() => {}} />)
    expect(screen.getByRole('heading', { name: /verify you're human/i })).toBeInTheDocument()
    expect(screen.getByText(/human check/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    await waitFor(() => expect(renderMock).toHaveBeenCalledTimes(1))
    expect(lastOpts.sitekey).toBe('1x00AA')
  })

  it("regression: does NOT pass appearance:'managed' (it threw 'Unknown appearance value' and broke the gate)", async () => {
    render(<TurnstileGate open siteKey="1x00AA" onVerified={() => {}} onCancel={() => {}} />)
    await waitFor(() => expect(renderMock).toHaveBeenCalledTimes(1))
    // 'managed' is the dashboard widget MODE, never a valid render `appearance`.
    expect(lastOpts.appearance).not.toBe('managed')
    // Either omitted (default 'always') or one of the valid values — never invalid.
    if (lastOpts.appearance !== undefined) {
      expect(['always', 'execute', 'interaction-only']).toContain(lastOpts.appearance)
    }
    // render() succeeded (didn't throw) → no retry alert; the gate is live.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('auto-proceeds: the widget callback forwards the token to onVerified after the success beat', async () => {
    const onVerified = vi.fn()
    render(<TurnstileGate open siteKey="k" onVerified={onVerified} onCancel={() => {}} />)
    await waitFor(() => expect(renderMock).toHaveBeenCalled())
    act(() => lastOpts.callback('tok-123'))
    // The host receives the token after the brief "Verified" beat (setTimeout).
    await waitFor(() => expect(onVerified).toHaveBeenCalledWith('tok-123'), { timeout: 2000 })
  })

  it('Cancel fires onCancel', () => {
    const onCancel = vi.fn()
    render(<TurnstileGate open siteKey="k" onVerified={() => {}} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('error-callback resets the widget and shows inline retry copy', async () => {
    render(<TurnstileGate open siteKey="k" onVerified={() => {}} onCancel={() => {}} />)
    await waitFor(() => expect(renderMock).toHaveBeenCalled())
    act(() => lastOpts['error-callback']())
    expect(resetMock).toHaveBeenCalledWith('widget-1')
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('does not render the widget while closed', () => {
    render(<TurnstileGate open={false} siteKey="k" onVerified={() => {}} onCancel={() => {}} />)
    expect(renderMock).not.toHaveBeenCalled()
  })

  it('is accessible (vitest-axe)', async () => {
    const { container } = render(
      <TurnstileGate open siteKey="k" onVerified={() => {}} onCancel={() => {}} />
    )
    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })
})
