import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { createReview as requestReview, listReviews, setFixDecision as requestSetFixDecision, getReview } from '../lib/api.js'
import { mapReview } from '../lib/reviewMapper.js'
import { useAuth } from './AuthContext.jsx'

const ReviewContext = createContext(null)
const SETTINGS_KEY = 'codeguard.settings.v1'

export const DEFAULT_SETTINGS = {
  defaultLanguage: 'javascript',
  editorFontSize: 13,
  wordWrap: false,
  minimap: false,
}

function readSettings() {
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function ReviewProvider({ children }) {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const [reviews, setReviews] = useState([])
  const [historyState, setHistoryState] = useState('loading')
  const [historyError, setHistoryError] = useState('')
  const [apiAvailable, setApiAvailable] = useState(true)
  const [settings, setSettings] = useState(() => ({
    ...DEFAULT_SETTINGS,
    ...readSettings(),
  }))

  useEffect(() => {
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
    } catch {
      // Preferences stay in memory when storage is unavailable.
    }
  }, [settings])

  const refreshReviews = useCallback(async () => {
    setHistoryState('loading')
    setHistoryError('')
    try {
      const data = await listReviews({ limit: 50 })
      setReviews((data?.items ?? []).map(mapReview).filter(Boolean))
      setHistoryState('ready')
      setApiAvailable(true)
    } catch (error) {
      setHistoryState('error')
      setHistoryError(error.message)
      setApiAvailable(false)
    }
  }, [])

  // Reviews are per-account: load them only once the signed-in user is known,
  // and drop the cache on sign-out so the next account never sees them.
  useEffect(() => {
    if (!userId) {
      setReviews([])
      setHistoryState('idle')
      setHistoryError('')
      return
    }
    void refreshReviews()
  }, [userId, refreshReviews])

  const createReview = useCallback(async ({ code, language, filename }) => {
    const response = await requestReview({ code, language, filename })
    const review = mapReview(response)
    setReviews((previous) => [review, ...previous.filter((item) => item.id !== review.id)])
    setHistoryState('ready')
    setApiAvailable(true)
    return review
  }, [])

  const setFixDecision = useCallback(async ({ reviewId, findingId, decision }) => {
    const response = await requestSetFixDecision({ reviewId, findingId, decision })
    const review = mapReview(response)
    setReviews((previous) => previous.map((item) => (item.id === review.id ? review : item)))
    setHistoryState('ready')
    setApiAvailable(true)
    return review
  }, [])

  const fetchReview = useCallback(async (reviewId) => {
    const response = await getReview(reviewId)
    const review = mapReview(response)
    setReviews((previous) => {
      const exists = previous.some((item) => item.id === review.id)
      return exists ? previous.map((item) => (item.id === review.id ? review : item)) : [review, ...previous]
    })
    return review
  }, [])

  const updateSettings = useCallback((patch) => {
    setSettings((previous) => ({ ...previous, ...patch }))
  }, [])

  const resetSettings = useCallback(() => {
    setSettings({ ...DEFAULT_SETTINGS })
  }, [])

  const value = useMemo(
    () => ({
      reviews,
      createReview,
      setFixDecision,
      fetchReview,
      refreshReviews,
      historyState,
      historyError,
      apiAvailable,
      settings,
      updateSettings,
      resetSettings,
    }),
    [
      reviews,
      createReview,
      setFixDecision,
      fetchReview,
      refreshReviews,
      historyState,
      historyError,
      apiAvailable,
      settings,
      updateSettings,
      resetSettings,
    ],
  )

  return <ReviewContext.Provider value={value}>{children}</ReviewContext.Provider>
}

export function useReviews() {
  const context = useContext(ReviewContext)
  if (!context) {
    throw new Error('useReviews must be used inside a ReviewProvider')
  }
  return context
}
