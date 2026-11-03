import { AlertTriangle, Ban, Check, Clock, Loader2, MinusCircle } from 'lucide-react'
import { cn } from '../lib/cn.js'
import { formatDuration } from '../lib/format.js'

const STATUS = {
  idle: { label: 'Idle', className: 'border-ink-700 bg-ink-800/80 text-mist-400' },
  running: { label: 'Analyzing', className: 'border-brand-500/30 bg-brand-500/10 text-brand-200' },
  pending: {
    label: 'Awaiting AI',
    className: 'border-amber-500/25 bg-amber-500/10 text-amber-200',
  },
  'awaiting ai': {
    label: 'Awaiting AI',
    className: 'border-amber-500/25 bg-amber-500/10 text-amber-200',
  },
  complete: {
    label: 'Complete',
    className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  },
  completed: {
    label: 'Complete',
    className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  },
  ok: {
    label: 'Complete',
    className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  },
  failed: { label: 'Failed', className: 'border-rose-500/30 bg-rose-500/10 text-rose-300' },
  error: { label: 'Failed', className: 'border-rose-500/30 bg-rose-500/10 text-rose-300' },
  timeout: { label: 'Timed out', className: 'border-orange-500/30 bg-orange-500/10 text-orange-300' },
  skipped: { label: 'Skipped', className: 'border-ink-600 bg-ink-800/60 text-mist-400' },
  'not reported': { label: 'Not reported', className: 'border-ink-700 bg-ink-800/40 text-mist-500' },
}

function normalizeStatus(status) {
  if (!status) return 'idle'
  const normalized = String(status).toLowerCase().replace(/_/g, ' ')
  if (normalized === 'ok') return 'ok'
  if (normalized === 'complete' || normalized === 'completed') return 'complete'
  if (normalized === 'failed' || normalized === 'error') return 'failed'
  if (normalized === 'timeout' || normalized === 'timed out') return 'timeout'
  if (normalized === 'skipped') return 'skipped'
  if (normalized === 'pending' || normalized === 'awaiting ai') return 'pending'
  if (normalized === 'running' || normalized === 'analyzing') return 'running'
  if (normalized === 'not reported' || normalized === 'missing') return 'not reported'
  return normalized
}

function StatusIcon({ status }) {
  const normalized = normalizeStatus(status)
  if (normalized === 'running') return <Loader2 className="h-2.5 w-2.5 animate-spin" aria-hidden="true" />
  if (normalized === 'complete') return <Check className="h-2.5 w-2.5" aria-hidden="true" />
  if (normalized === 'pending') return <Clock className="h-2.5 w-2.5" aria-hidden="true" />
  if (normalized === 'failed') return <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
  if (normalized === 'timeout') return <Clock className="h-2.5 w-2.5" aria-hidden="true" />
  if (normalized === 'skipped') return <MinusCircle className="h-2.5 w-2.5" aria-hidden="true" />
  if (normalized === 'not reported') return <Ban className="h-2.5 w-2.5" aria-hidden="true" />
  return null
}

/**
 * One pipeline agent with its current run status.
 */
export default function AgentCard({
  agent,
  status = 'idle',
  findings = 0,
  durationMs,
  summary,
  errorMessage,
}) {
  const Icon = agent?.icon
  const normalizedStatus = normalizeStatus(status)
  const statusConfig = STATUS[normalizedStatus] ?? STATUS.idle

  const isComplete = normalizedStatus === 'complete'
  const isRunning = normalizedStatus === 'running'
  const isFailed = normalizedStatus === 'failed'
  const isTimeout = normalizedStatus === 'timeout'
  const isSkipped = normalizedStatus === 'skipped'
  const isPending = normalizedStatus === 'pending'
  const isNotReported = normalizedStatus === 'not reported'

  return (
    <article
      className={cn(
        'relative overflow-hidden rounded-xl border bg-ink-850/60 p-3.5 transition-colors duration-200',
        isRunning
          ? 'border-brand-500/40'
          : 'border-ink-700/80 hover:border-ink-600/80',
      )}
    >
      {isRunning ? (
        <span
          className="absolute inset-x-0 top-0 h-px animate-pulse bg-gradient-to-r from-transparent via-brand-400 to-transparent"
          aria-hidden="true"
        />
      ) : null}

      <div className="flex items-start gap-3">
        <span
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border',
            agent?.tone?.icon || 'border-ink-700 bg-ink-800/80 text-mist-400',
          )}
        >
          {Icon ? <Icon className="h-4 w-4" aria-hidden="true" /> : null}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm leading-snug font-semibold text-mist-100">
              {agent?.name || 'Agent'}
            </h3>
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
                statusConfig.className,
              )}
            >
              <StatusIcon status={normalizedStatus} />
              {statusConfig.label}
            </span>
          </div>

          <p className="mt-1 hidden text-xs leading-relaxed text-mist-500 sm:block">
            {agent?.description || 'No description available.'}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-mist-500">
            <span>
              {isComplete
                ? `${findings ?? 0} ${(findings ?? 0) === 1 ? 'finding' : 'findings'}`
                : isRunning
                  ? 'Analyzing snippet…'
                  : isPending
                    ? 'No analysis yet'
                    : isFailed
                      ? 'Analysis failed'
                      : isTimeout
                        ? 'Execution timed out'
                        : isSkipped
                          ? 'Skipped'
                          : isNotReported
                            ? 'Not reported'
                            : 'Awaiting run'}
            </span>
            {isComplete && durationMs != null ? (
              <>
                <span className="h-1 w-1 rounded-full bg-ink-500" aria-hidden="true" />
                <span>{formatDuration(durationMs)}</span>
              </>
            ) : null}
            {durationMs != null && !isComplete ? (
              <>
                <span className="h-1 w-1 rounded-full bg-ink-500" aria-hidden="true" />
                <span>{formatDuration(durationMs)}</span>
              </>
            ) : null}
          </div>

          {summary && (isComplete || isFailed || isTimeout) ? (
            <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-mist-400">
              {summary}
            </p>
          ) : null}

          {(errorMessage || (isFailed && !summary)) && !isNotReported ? (
            <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-rose-300/80">
              {errorMessage || 'Agent execution failed.'}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  )
}

export { normalizeStatus }
