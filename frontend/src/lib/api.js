/**
 * Centralized API client for the CodeGuard backend.
 */

const DEFAULT_BASE_URL = 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 15_000

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(
  /\/+$/,
  '',
)

export class ApiError extends Error {
  constructor(message, { status = 0, detail = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function firstDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const item = detail[0]
    const location = Array.isArray(item.loc)
      ? item.loc.filter((part) => part !== 'body').join('.')
      : ''
    return `${location ? `${location}: ` : ''}${item.msg ?? 'Invalid request.'}`
  }
  return null
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const abortFromCaller = () => controller.abort()
  signal?.addEventListener('abort', abortFromCaller)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })

    const text = await response.text()
    let data = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = null
    }

    if (!response.ok) {
      const detail = firstDetail(data?.detail)
      throw new ApiError(
        detail ?? `The review service returned HTTP ${response.status}.`,
        { status: response.status, detail: data?.detail ?? null },
      )
    }

    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error.name === 'AbortError') {
      throw new ApiError('The request timed out. Check that the backend is running.', {
        status: 0,
      })
    }
    throw new ApiError(
      `Cannot reach the CodeGuard API at ${API_BASE_URL}. Start the backend and try again.`,
      { status: 0 },
    )
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abortFromCaller)
  }
}

export function getHealth() {
  return request('/health')
}

export function createReview({ code, language, filename }) {
  return request('/api/review', {
    method: 'POST',
    body: { code, language, filename: filename ?? null },
  })
}

export function listReviews({ limit = 50, offset = 0, language } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (language) params.set('language', language)
  return request(`/api/reviews?${params.toString()}`)
}

export function getReview(reviewId) {
  return request(`/api/reviews/${encodeURIComponent(reviewId)}`)
}
