import type { Filters } from './types'
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, credentials: 'same-origin', headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers } })
  if (!response.ok) {
    let detail = 'The request could not be completed. Please try again.'
    try { const body = await response.json(); if (typeof body.detail === 'string') detail = body.detail } catch { /* Non-JSON error retains accessible fallback. */ }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204 || response.headers.get('Content-Length') === '0') return undefined as T
  return response.json() as Promise<T>
}
export function queryString(filters: Filters): string {
  const params = new URLSearchParams({ q: filters.q.trim(), freshness: filters.freshness })
  if (filters.bbox) params.set('bbox', filters.bbox.join(','))
  return params.toString()
}
export function dateLabel(value: string | null): string {
  if (!value) return 'Not reported'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not reported'
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date)
}
export function fieldLabel(value: string): string { return value.replaceAll('_', ' ') }
export function safeSourceUrl(value: string): string | undefined {
  if (/^\/api\/sources\/[a-zA-Z0-9_-]+$/.test(value)) return value
  return undefined
}
