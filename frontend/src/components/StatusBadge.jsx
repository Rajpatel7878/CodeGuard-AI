import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import { cn } from '../lib/cn.js'

const STATUS = {
  pending: {
    label: 'Analysis pending',
    className: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    Icon: Clock,
  },
  completed: {
    label: 'Completed',
    className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    Icon: CheckCircle2,
  },
  failed: {
    label: 'Failed',
    className: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
    Icon: AlertTriangle,
  },
}

export default function StatusBadge({ status = 'pending', label, className }) {
  const config = STATUS[status] ?? STATUS.pending
  const Icon = config.Icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
        config.className,
        className,
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label ?? config.label}
    </span>
  )
}
