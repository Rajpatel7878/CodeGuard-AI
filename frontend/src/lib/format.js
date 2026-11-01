export function formatRelativeTime(timestamp) {
  if (!timestamp) return '—'
  const diff = Date.now() - new Date(timestamp).getTime()
  const minute = 60_000
  const hour = 60 * minute
  const day = 24 * hour

  if (diff < minute) return 'Just now'
  if (diff < hour) {
    const minutes = Math.round(diff / minute)
    return `${minutes} min ago`
  }
  if (diff < day) {
    const hours = Math.round(diff / hour)
    return `${hours} hr ago`
  }
  if (diff < 7 * day) {
    const days = Math.round(diff / day)
    return `${days} day${days === 1 ? '' : 's'} ago`
  }
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(
    new Date(timestamp),
  )
}

export function formatDateTime(timestamp) {
  if (!timestamp) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp))
}

export function formatDuration(milliseconds) {
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) return '—'
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`
  return `${(milliseconds / 1000).toFixed(1)} s`
}

export function formatNumber(value) {
  return new Intl.NumberFormat().format(value ?? 0)
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return count === 1 ? singular : plural
}
