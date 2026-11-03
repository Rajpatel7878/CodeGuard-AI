/**
 * Centralized API client for the CodeGuard backend.
 */

const DEFAULT_BASE_URL = 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 15_000
// A review runs four AI agents and the fix agent against Gemini, each with its
// own timeout and retry budget; 15s would abort a review that is still working.
const REVIEW_TIMEOUT_MS = 300_000

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

async function request(path, { method = 'GET', body, signal, timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const abortFromCaller = () => controller.abort()
  signal?.addEventListener('abort', abortFromCaller)

  try {
    const token = localStorage.getItem('token')
    const headers = {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    }
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      credentials: 'include',
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
      if (response.status === 401) {
        throw new ApiError('Your session has expired. Sign in again.', {
          status: 401,
          detail: data?.detail ?? null,
        })
      }
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
      throw new ApiError(
        'The request timed out before the API responded. Check that the backend is running and try again.',
        { status: 0 },
      )
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
    timeoutMs: REVIEW_TIMEOUT_MS,
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

export function setFixDecision({ reviewId, findingId, decision }) {
  const params = new URLSearchParams({ decision, finding_id: findingId })
  return request(`/api/reviews/${encodeURIComponent(reviewId)}/fix-decision?${params.toString()}`, {
    method: 'POST',
  })
}
