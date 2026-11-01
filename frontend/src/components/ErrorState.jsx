import { AlertTriangle, RefreshCw } from 'lucide-react'
import { cn } from '../lib/cn.js'

export default function ErrorState({
  title = 'Could not load reviews',
  message,
  onRetry,
  retryLabel = 'Try again',
  className,
}) {
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center justify-center px-6 py-12 text-center', className)}
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-rose-500/25 bg-rose-500/10">
        <AlertTriangle className="h-5 w-5 text-rose-300" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-sm font-semibold text-mist-100">{title}</h2>
      {message ? (
        <p className="mt-1.5 max-w-md text-xs leading-relaxed text-mist-400">{message}</p>
      ) : null}
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn btn-secondary mt-5 text-xs">
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {retryLabel}
        </button>
      ) : null}
    </div>
  )
}
