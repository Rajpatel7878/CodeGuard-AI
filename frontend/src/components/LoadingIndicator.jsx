import { Loader2 } from 'lucide-react'
import { cn } from '../lib/cn.js'

export default function LoadingIndicator({ label = 'Loading…', description, className }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex flex-col items-center justify-center gap-3 text-center', className)}
    >
      <Loader2 className="h-5 w-5 animate-spin text-brand-400" aria-hidden="true" />
      <div>
        <p className="text-sm font-medium text-mist-200">{label}</p>
        {description ? <p className="mt-1 text-xs text-mist-500">{description}</p> : null}
      </div>
    </div>
  )
}
