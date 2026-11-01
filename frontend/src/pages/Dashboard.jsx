import { useMemo } from 'react'
import {
  Activity,
  ChevronRight,
  FileCode2,
  FileSearch,
  Gauge,
  Plus,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import EmptyState from '../components/EmptyState.jsx'
import ErrorState from '../components/ErrorState.jsx'
import LoadingIndicator from '../components/LoadingIndicator.jsx'
import ScoreCard from '../components/ScoreCard.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { useReviews } from '../context/ReviewContext.jsx'
import { AGENTS } from '../data/agents.jsx'
import { cn } from '../lib/cn.js'
import { formatNumber, formatRelativeTime } from '../lib/format.js'
import { scoreClasses, scoreDescriptor } from '../lib/score.js'

export default function Dashboard() {
  const { reviews, historyState, historyError, refreshReviews } = useReviews()

  const stats = useMemo(() => {
    const totals = reviews.reduce(
      (accumulator, review) => {
        accumulator.critical += review.counts?.critical ?? 0
        accumulator.security += (review.issues ?? []).filter(
          (issue) => issue.agentId === 'security',
        ).length
        return accumulator
      },
      { critical: 0, security: 0 },
    )

    const scored = reviews.filter((review) => typeof review.score === 'number')
    const scoreSum = scored.reduce((sum, review) => sum + review.score, 0)

    return {
      total: reviews.length,
      critical: totals.critical,
      security: totals.security,
      averageScore: scored.length ? Math.round(scoreSum / scored.length) : null,
      pending: reviews.filter((review) => review.status === 'pending').length,
    }
  }, [reviews])

  const activity = useMemo(() => {
    const rows = AGENTS.map((agent) => {
      const findings = reviews.reduce(
        (sum, review) =>
          sum + (review.issues ?? []).filter((issue) => issue.agentId === agent.id).length,
        0,
      )
      const runs = reviews.filter((review) =>
        (review.agents ?? []).some((entry) => entry.id === agent.id),
      ).length
      return { agent, findings, runs }
    })
    const max = Math.max(1, ...rows.map((row) => row.findings))
    return { rows, max }
  }, [reviews])

  const recent = reviews.slice(0, 5)
  const initialLoading = historyState === 'loading' && reviews.length === 0

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Team ALPHA workspace</p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Dashboard
          </h1>
          <p className="mt-1.5 text-sm text-mist-400">
            Review health across every submission stored by the API.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/history" className="btn btn-secondary">
            History
          </Link>
          <Link to="/review" className="btn btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" />
            New review
          </Link>
        </div>
      </div>

      {historyState === 'error' && reviews.length > 0 ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 text-xs text-amber-200">
          <span>Could not refresh history. Showing the last loaded reviews.</span>
          <button type="button" onClick={() => void refreshReviews()} className="btn btn-ghost px-2.5 py-1 text-xs">
            Retry
          </button>
        </div>
      ) : null}

      {stats.pending > 0 && !initialLoading ? (
        <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 text-xs leading-relaxed text-mist-300">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" aria-hidden="true" />
          <p>
            {stats.pending} {stats.pending === 1 ? 'review is' : 'reviews are'} awaiting AI
            analysis. Findings and quality scores appear once an LLM provider is configured.
          </p>
        </div>
      ) : null}

      {initialLoading ? (
        <div className="card mt-6">
          <LoadingIndicator
            label="Loading reviews"
            description="Fetching history from the CodeGuard API."
            className="py-20"
          />
        </div>
      ) : historyState === 'error' && reviews.length === 0 ? (
        <div className="card mt-6">
          <ErrorState
            title="Review API unavailable"
            message={historyError}
            onRetry={() => void refreshReviews()}
          />
        </div>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <ScoreCard
              label="Total reviews"
              value={formatNumber(stats.total)}
              hint={
                stats.total === 0
                  ? 'Submit your first review to populate the workspace.'
                  : 'Stored in the API database.'
              }
              icon={FileSearch}
              tone="brand"
            />
            <ScoreCard
              label="Critical issues"
              value={formatNumber(stats.critical)}
              hint="Critical findings across stored reviews."
              icon={ShieldAlert}
              tone="rose"
            />
            <ScoreCard
              label="Security issues"
              value={formatNumber(stats.security)}
              hint="Findings raised by the Security Analysis Agent."
              icon={ShieldCheck}
              tone="amber"
            />
            <ScoreCard
              label="Avg quality score"
              value={stats.averageScore ?? '—'}
              suffix={stats.averageScore === null ? undefined : '/100'}
              hint={
                stats.averageScore === null
                  ? 'Awaiting AI analysis'
                  : scoreDescriptor(stats.averageScore)
              }
              icon={Gauge}
              tone="emerald"
              progress={stats.averageScore ?? 0}
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <section className="card overflow-hidden xl:col-span-2">
              <header className="flex items-center justify-between gap-3 border-b border-ink-700/80 px-4 py-3.5 sm:px-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Activity className="h-4 w-4 text-mist-400" aria-hidden="true" />
                  Recent reviews
                </h2>
                <Link
                  to="/history"
                  className="inline-flex items-center gap-1 text-xs font-medium text-brand-300 transition-colors hover:text-brand-200"
                >
                  View all
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </header>

              {recent.length === 0 ? (
                <EmptyState
                  title="No reviews yet"
                  description="Submit a snippet or upload a file to create a review record."
                  action={
                    <Link to="/review" className="btn btn-primary">
                      <Plus className="h-4 w-4" aria-hidden="true" />
                      Submit a review
                    </Link>
                  }
                />
              ) : (
                <ul className="divide-y divide-ink-700/60">
                  {recent.map((review) => (
                    <li key={review.id}>
                      <Link
                        to={`/results/${review.id}`}
                        className="group flex items-center gap-3 px-4 py-3.5 transition-colors hover:bg-ink-800/50 sm:px-5"
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-ink-700 bg-ink-800/70 text-mist-400">
                          <FileCode2 className="h-4 w-4" aria-hidden="true" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="truncate text-sm font-medium text-mist-100">
                              {review.filename ?? `${review.languageLabel} review`}
                            </p>
                            {review.status === 'pending' ? (
                              <StatusBadge status="pending" label="Pending" className="shrink-0" />
                            ) : null}
                          </div>
                          <p className="mt-0.5 text-[11px] text-mist-500">
                            {review.languageLabel} · {formatRelativeTime(review.createdAt)} ·{' '}
                            {review.counts?.total ?? 0} findings
                          </p>
                        </div>
                        <span
                          className={cn(
                            'inline-flex min-w-10 justify-center rounded-md border px-1.5 py-1 text-xs font-semibold tabular-nums',
                            scoreClasses(review.score),
                          )}
                          title={
                            review.score === null
                              ? 'Quality score pending analysis'
                              : `Quality score ${review.score}/100`
                          }
                        >
                          {review.score ?? '—'}
                        </span>
                        <ChevronRight
                          className="h-4 w-4 shrink-0 text-mist-500 transition-transform group-hover:translate-x-0.5"
                          aria-hidden="true"
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="space-y-4">
              <section className="card p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-white">Agent activity</h2>
                    <p className="mt-1 text-xs text-mist-500">
                      Findings raised by each agent across stored reviews.
                    </p>
                  </div>
                  <span className="chip shrink-0">{reviews.length} runs</span>
                </div>

                <ul className="mt-5 space-y-4">
                  {activity.rows.map(({ agent, findings, runs }) => {
                    const Icon = agent.icon
                    return (
                      <li key={agent.id}>
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              'flex h-6 w-6 shrink-0 items-center justify-center rounded-md border',
                              agent.tone.icon,
                            )}
                          >
                            <Icon className="h-3 w-3" aria-hidden="true" />
                          </span>
                          <p className="flex-1 truncate text-xs font-medium text-mist-200">
                            {agent.shortName}
                          </p>
                          <span className="text-[11px] tabular-nums text-mist-400">{findings}</span>
                        </div>
                        <div
                          className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-800"
                          aria-hidden="true"
                        >
                          <div
                            className={cn('h-full rounded-full', agent.tone.bar)}
                            style={{ width: `${Math.round((findings / activity.max) * 100)}%` }}
                          />
                        </div>
                        <p className="mt-1 text-[10px] text-mist-500">
                          {runs} {runs === 1 ? 'run' : 'runs'}
                        </p>
                      </li>
                    )
                  })}
                </ul>

                <p className="mt-4 border-t border-ink-700/70 pt-3 text-[11px] leading-relaxed text-mist-500">
                  Findings stay at zero until AI analysis is configured.
                </p>
              </section>

              <section className="card p-5">
                <h2 className="text-sm font-semibold text-white">Pipeline</h2>
                <p className="mt-1 text-xs text-mist-500">
                  Five agents are registered for every review.
                </p>
                <ul className="mt-3 space-y-2">
                  {AGENTS.map((agent) => {
                    const Icon = agent.icon
                    return (
                      <li key={agent.id} className="flex items-center gap-2 text-xs text-mist-300">
                        <Icon
                          className={cn('h-3.5 w-3.5 shrink-0', agent.tone.text)}
                          aria-hidden="true"
                        />
                        <span className="truncate">{agent.name}</span>
                      </li>
                    )
                  })}
                </ul>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
