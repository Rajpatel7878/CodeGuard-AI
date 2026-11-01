import { FileSearch } from 'lucide-react'
import { cn } from '../lib/cn.js'

export default function EmptyState({
  icon: Icon = FileSearch,
  title,
  description,
  action,
  className,
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-12 text-center', className)}>
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-ink-700 bg-ink-800/80">
        <Icon className="h-5 w-5 text-mist-400" aria-hidden="true" />
      </span>
      <h3 className="mt-4 text-sm font-semibold text-mist-100">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-mist-500">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}
