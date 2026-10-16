import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { submitScan } from '@/lib/api/scans'
import { useRepoScanFlow } from '@/lib/hooks/useRepoScanFlow'

vi.mock('@/lib/api/scans', () => ({ submitScan: vi.fn() }))

describe('useRepoScanFlow', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(submitScan).mockResolvedValue({
      id: 'run-1',
      status: 'pending',
      cached: false,
      rubric_version: '1',
      submitted_at: '2026-10-16T12:00:00Z',
    })
  })

  it.each([
    ['n8n-io/n8n', 'https://github.com/n8n-io/n8n'],
    ['github.com/n8n-io/n8n', 'https://github.com/n8n-io/n8n'],
    ['www.github.com/n8n-io/n8n', 'https://github.com/n8n-io/n8n'],
    ['https://www.github.com/n8n-io/n8n', 'https://github.com/n8n-io/n8n'],
    ['http://www.github.com/n8n-io/n8n', 'http://github.com/n8n-io/n8n'],
    ['https://github.com/n8n-io/n8n', 'https://github.com/n8n-io/n8n'],
    ['http://github.com/n8n-io/n8n', 'http://github.com/n8n-io/n8n'],
    ['  github.com/n8n-io/n8n  ', 'https://github.com/n8n-io/n8n'],
    [
      'www.github.com/Acme/Repo.git/tree/main/skills/',
      'https://github.com/Acme/Repo.git/tree/main/skills/',
    ],
  ])('submits %s as %s', async (input, expected) => {
    const { result } = renderHook(() => useRepoScanFlow())
    const onResult = vi.fn()
    act(() => result.current.setUrlValue(input))
    await act(() =>
      result.current.submit({ visibility: 'unlisted', captchaToken: 'verified', onResult })
    )

    expect(submitScan).toHaveBeenCalledExactlyOnceWith(
      { github_url: expected, visibility: 'unlisted' },
      'verified'
    )
    expect(onResult).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ id: 'run-1' }))
    expect(result.current.urlError).toBeNull()
    expect(result.current.submitting).toBe(true)
  })

  it.each([
    '',
    'https://gitlab.com/n8n-io/n8n',
    'https://github.com.evil.example/n8n-io/n8n',
    'https://github.com@evil.example/n8n-io/n8n',
    'https://evil.example/github.com/n8n-io/n8n',
    'ftp://github.com/n8n-io/n8n',
    'github.com/n8n-io/',
    'github.com/n8n-io/n8 n',
  ])('rejects invalid input %s without submitting', async (input) => {
    const { result } = renderHook(() => useRepoScanFlow())
    const onResult = vi.fn()
    act(() => result.current.setUrlValue(input))
    await act(() => result.current.submit({ visibility: 'public', onResult }))

    expect(submitScan).not.toHaveBeenCalled()
    expect(onResult).not.toHaveBeenCalled()
    expect(result.current.urlError).toContain('Paste a public github.com URL')
    expect(result.current.submitting).toBe(false)
  })
})
