import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { createReview as requestReview, listReviews } from '../lib/api.js'
import { mapReview } from '../lib/reviewMapper.js'

const ReviewContext = createContext(null)
const SETTINGS_KEY = 'codeguard.settings.v1'

export const DEFAULT_SETTINGS = {
  defaultLanguage: 'javascript',
  editorFontSize: 13,
  wordWrap: false,
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

  useEffect(() => {
    void refreshReviews()
  }, [refreshReviews])

  const createReview = useCallback(async ({ code, language, filename }) => {
    const response = await requestReview({ code, language, filename })
    const review = mapReview(response)
    setReviews((previous) => [review, ...previous.filter((item) => item.id !== review.id)])
    setHistoryState('ready')
    setApiAvailable(true)
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
