import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, dateLabel, fieldLabel, queryString, safeSourceUrl } from './api'
afterEach(() => vi.unstubAllGlobals())
describe('API client', () => {
  it('sends same-origin credentials and JSON content type', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ authenticated: true })))
    vi.stubGlobal('fetch', fetcher)
    await expect(api('/login', { method: 'POST', body: JSON.stringify({ role: 'reader' }) })).resolves.toEqual({ authenticated: true })
    expect(fetcher).toHaveBeenCalledWith('/api/login', expect.objectContaining({ credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }))
  })
  it('accepts empty logout responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(api('/logout', { method: 'POST' })).resolves.toBeUndefined()
  })
  it('retains actionable API errors and status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 })))
    await expect(api('/records')).rejects.toMatchObject({ message: 'Session expired', status: 401 })
  })
  it('handles non-JSON errors without rendering the server body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Failure</html>', { status: 502 })))
    await expect(api('/records')).rejects.toBeInstanceOf(ApiError)
  })
})
describe('display and query safety', () => {
  it('escapes filters and serializes bounding boxes', () => {
    const query = new URLSearchParams(queryString({ q: '  A&B ', freshness: 'stale', bbox: [-75.8,45.34,-75.59,45.49] }))
    expect(query.get('q')).toBe('A&B'); expect(query.get('freshness')).toBe('stale'); expect(query.get('bbox')).toBe('-75.8,45.34,-75.59,45.49')
  })
  it('handles missing dates and presents valid dates in UTC', () => {
    expect(dateLabel(null)).toBe('Not reported'); expect(dateLabel('bad')).toBe('Not reported'); expect(dateLabel('2026-10-11T23:00:00Z')).toBe('11 Oct 2026')
    expect(fieldLabel('community_centre')).toBe('community centre')
  })
  it('permits only local authenticated source references', () => {
    expect(safeSourceUrl('/api/sources/SRC-001')).toBe('/api/sources/SRC-001')
    for (const url of ['javascript:alert(1)', '//evil.example/a', 'https://external.example/a', '/api/sources/../records', '/api/sources/x?token=secret', '/api/sources/%2e%2e']) expect(safeSourceUrl(url)).toBeUndefined()
  })
})
