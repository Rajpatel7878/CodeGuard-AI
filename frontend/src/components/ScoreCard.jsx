import { cn } from '../lib/cn.js'

const TONES = {
  brand: {
    icon: 'border-brand-500/20 bg-brand-500/10 text-brand-300',
    bar: 'bg-brand-500',
  },
  rose: {
    icon: 'border-rose-500/20 bg-rose-500/10 text-rose-300',
    bar: 'bg-rose-400',
  },
  amber: {
    icon: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
    bar: 'bg-amber-400',
  },
  emerald: {
    icon: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
    bar: 'bg-emerald-400',
  },
  sky: {
    icon: 'border-sky-500/20 bg-sky-500/10 text-sky-300',
    bar: 'bg-sky-400',
  },
  violet: {
    icon: 'border-violet-500/20 bg-violet-500/10 text-violet-300',
    bar: 'bg-violet-400',
  },
}

/**
 * Generic metric card used by the dashboard and the results summary.
 */
export default function ScoreCard({
  label,
  value,
  suffix,
  hint,
  icon: Icon,
  tone = 'brand',
  progress,
  className,
}) {
  const palette = TONES[tone] ?? TONES.brand
  const clampedProgress =
    typeof progress === 'number' ? Math.min(100, Math.max(0, progress)) : null

  return (
    <article className={cn('card p-5', className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-wider text-mist-400 uppercase">{label}</p>
          <p className="mt-2 flex items-baseline gap-1.5 text-3xl font-semibold tracking-tight text-white">
            <span className="tabular-nums">{value}</span>
            {suffix ? (
              <span className="text-base font-medium text-mist-400">{suffix}</span>
            ) : null}
          </p>
        </div>
        {Icon ? (
          <span
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border',
              palette.icon,
            )}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
        ) : null}
      </div>

      {clampedProgress !== null ? (
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-ink-800" aria-hidden="true">
          <div
            className={cn('h-full rounded-full transition-all duration-500', palette.bar)}
            style={{ width: `${clampedProgress}%` }}
          />
        </div>
      ) : null}

      {hint ? <p className="mt-3 text-xs leading-relaxed text-mist-500">{hint}</p> : null}
    </article>
  )
}
