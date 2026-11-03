import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, FileCode2, Plus, Search, SlidersHorizontal, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import EmptyState from '../components/EmptyState.jsx'
import ErrorState from '../components/ErrorState.jsx'
import LoadingIndicator from '../components/LoadingIndicator.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { useReviews } from '../context/ReviewContext.jsx'
import { cn } from '../lib/cn.js'
import { formatRelativeTime } from '../lib/format.js'
import { getLanguage } from '../lib/languages.js'
import { scoreClasses } from '../lib/score.js'

export default function ReviewHistory() {
  const { reviews, historyState, historyError, refreshReviews } = useReviews()
  const [query, setQuery] = useState('')
  const [languageFilter, setLanguageFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 10

  const languages = useMemo(
    () => [...new Set(reviews.map((review) => review.language))],
    [reviews],
  )

  const filtered = useMemo(() => {
    const search = query.trim().toLowerCase()
    return reviews.filter((review) => {
      const haystack = [
        review.filename,
        review.languageLabel,
        review.id,
        review.grade,
        review.status,
        ...(review.issues ?? []).map((issue) => issue.title),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      const matchesQuery = !search || haystack.includes(search)
      const matchesLanguage = languageFilter === 'all' || review.language === languageFilter
      const matchesStatus = statusFilter === 'all' || review.status === statusFilter
      return matchesQuery && matchesLanguage && matchesStatus
    })
  }, [reviews, query, languageFilter, statusFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / itemsPerPage))
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage
    return filtered.slice(start, start + itemsPerPage)
  }, [filtered, currentPage])

  useEffect(() => {
    setCurrentPage(1)
  }, [query, languageFilter, statusFilter])

  const filtersActive = query.trim() !== '' || languageFilter !== 'all' || statusFilter !== 'all'

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Review history
          </h1>
          <p className="mt-1.5 text-sm text-mist-400">
            Every review stored by the API, newest first.
          </p>
        </div>
        <Link to="/review" className="btn btn-primary w-fit">
          <Plus className="h-4 w-4" aria-hidden="true" />
          New review
        </Link>
      </div>

      {historyState === 'error' && reviews.length === 0 ? (
        <div className="card mt-6">
          <ErrorState
            title="Review API unavailable"
            message={historyError}
            onRetry={() => void refreshReviews()}
          />
        </div>
      ) : historyState === 'loading' && reviews.length === 0 ? (
        <div className="card mt-6">
          <LoadingIndicator
            label="Loading history"
            description="Fetching stored reviews from the API."
            className="py-20"
          />
        </div>
      ) : (
        <>
          {historyState === 'error' ? (
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 text-xs text-amber-200">
              <span>Could not refresh history. Showing the last loaded reviews.</span>
              <button
                type="button"
                onClick={() => void refreshReviews()}
                className="btn btn-ghost px-2.5 py-1 text-xs"
              >
                Retry
              </button>
            </div>
          ) : null}

          <div className="card mt-6 p-3.5 sm:p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search
                  className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-mist-500"
                  aria-hidden="true"
                />
                <label htmlFor="history-search" className="sr-only">
                  Search reviews
                </label>
                <input
                  id="history-search"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by file, language, ID, or finding…"
                  className="field pl-9"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="history-language" className="sr-only">
                  Filter by language
                </label>
                <div className="relative">
                  <SlidersHorizontal
                    className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-mist-500"
                    aria-hidden="true"
                  />
                  <select
                    id="history-language"
                    value={languageFilter}
                    onChange={(event) => setLanguageFilter(event.target.value)}
                    className="field appearance-none py-2.5 pr-8 pl-8 text-xs sm:w-40"
                  >
                    <option value="all">All languages</option>
                    {languages.map((language) => (
                      <option key={language} value={language}>
                        {getLanguage(language).label}
                      </option>
                    ))}
                  </select>
                </div>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="field py-2.5 text-xs sm:w-36"
                >
                  <option value="all">All statuses</option>
                  <option value="completed">Completed</option>
                  <option value="completed_with_errors">Completed with errors</option>
                  <option value="pending">Pending</option>
                  <option value="error">Error</option>
                </select>

                {filtersActive ? (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('')
                      setLanguageFilter('all')
                      setStatusFilter('all')
                    }}
                    className="btn btn-ghost shrink-0 px-2.5 py-2 text-xs"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                    Clear
                  </button>
                ) : null}
              </div>
            </div>
          </div>

          <p className="mt-4 px-1 text-xs text-mist-500">
            Showing {paginatedItems.length} of {filtered.length}{' '}
            {filtered.length === 1 ? 'review' : 'reviews'}
            {filtered.length !== reviews.length ? ` (filtered from ${reviews.length})` : ''}
          </p>

          <section className="card mt-2 overflow-hidden">
            {reviews.length === 0 ? (
              <EmptyState
                title="No reviews stored"
                description="Submit a snippet and it will appear here."
                action={
                  <Link to="/review" className="btn btn-primary">
                    <Plus className="h-4 w-4" aria-hidden="true" />
                    Submit a review
                  </Link>
                }
              />
            ) : filtered.length === 0 ? (
              <EmptyState
                icon={Search}
                title="No matching reviews"
                description="Try a different search term or clear the filters."
                action={
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('')
                      setLanguageFilter('all')
                      setStatusFilter('all')
                    }}
                    className="btn btn-secondary"
                  >
                    Clear filters
                  </button>
                }
              />
            ) : (
              <>
                <div className="hidden grid-cols-[minmax(0,1fr)_8rem_6rem_5rem_7rem_1.5rem] gap-4 border-b border-ink-700/80 px-5 py-3 text-[10px] font-semibold tracking-wider text-mist-500 uppercase md:grid">
                  <span>Review</span>
                  <span>Language</span>
                  <span>Findings</span>
                  <span>Score</span>
                  <span>Submitted</span>
                  <span />
                </div>

                <ul className="divide-y divide-ink-700/60">
                  {paginatedItems.map((review) => (
                    <li key={review.id}>
                      <Link
                        to={`/results/${review.id}`}
                        className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3.5 transition-colors hover:bg-ink-800/50 sm:px-5 md:grid-cols-[minmax(0,1fr)_8rem_6rem_5rem_7rem_1.5rem] md:gap-4"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <FileCode2
                              className="h-3.5 w-3.5 shrink-0 text-mist-500"
                              aria-hidden="true"
                            />
                            <p className="truncate text-sm font-medium text-mist-100">
                              {review.filename ?? `${review.languageLabel} review`}
                            </p>
                            {review.status === 'pending' ? (
                              <StatusBadge
                                status="pending"
                                label="Pending"
                                className="shrink-0"
                              />
                            ) : null}
                          </div>
                          <p className="mt-0.5 truncate font-mono text-[11px] text-mist-500">
                            {review.id}
                          </p>
                          <p className="mt-1 text-[11px] text-mist-500 md:hidden">
                            {review.counts?.total ?? 0} findings ·{' '}
                            {formatRelativeTime(review.createdAt)}
                          </p>
                        </div>

                        <span className="hidden text-xs text-mist-300 md:block">
                          {review.languageLabel}
                        </span>
                        <span className="hidden text-xs tabular-nums text-mist-300 md:block">
                          {review.counts?.total ?? 0}
                        </span>
                        <span
                          className={cn(
                            'hidden w-fit min-w-10 justify-center rounded-md border px-1.5 py-1 text-center text-xs font-semibold tabular-nums md:inline-flex',
                            scoreClasses(review.score),
                          )}
                        >
                          {review.score ?? '—'}
                        </span>
                        <span className="hidden text-xs text-mist-400 md:block">
                          {formatRelativeTime(review.createdAt)}
                        </span>
                        <span className="hidden justify-end md:flex">
                          <ChevronRight
                            className="h-4 w-4 text-mist-500 transition-transform group-hover:translate-x-0.5"
                            aria-hidden="true"
                          />
                        </span>

                        <span
                          className={cn(
                            'inline-flex min-w-10 justify-self-end rounded-md border px-1.5 py-1 text-center text-xs font-semibold tabular-nums md:hidden',
                            scoreClasses(review.score),
                          )}
                        >
                          {review.score ?? '—'}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {totalPages > 1 ? (
                  <div className="flex items-center justify-between border-t border-ink-700/80 px-4 py-3 sm:px-5">
                    <p className="text-xs text-mist-500">
                      Page {currentPage} of {totalPages}
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="btn btn-ghost px-2.5 py-1.5 text-xs disabled:opacity-50"
                      >
                        <ChevronLeft className="h-3.5 w-3.5" />
                        Previous
                      </button>
                      <button
                        type="button"
                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="btn btn-ghost px-2.5 py-1.5 text-xs disabled:opacity-50"
                      >
                        Next
                        <ChevronRight className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      )}
    </div>
  )
}
