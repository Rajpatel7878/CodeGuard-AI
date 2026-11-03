import { Check, GitCompare, MapPin, Wrench, XCircle } from 'lucide-react'
import { cn } from '../lib/cn.js'
import { getSeverity } from '../lib/severity.js'

/**
 * A single finding with severity, source agent, and a suggested fix.
 */
export default function IssueCard({ issue, onClick, isSelected, onFixDecision }) {
  const severity = getSeverity(issue.severity)
  const line = issue.line || issue.startLine
  const suggestion = issue.suggestion || issue.suggestedFix

  return (
    <article
      className={cn(
        'card border-l-2 p-4 sm:p-5 transition-all cursor-pointer hover:border-ink-600',
        severity.rail,
        isSelected && 'ring-1 ring-brand-500/50',
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold',
            severity.badge,
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', severity.dot)} aria-hidden="true" />
          {severity.label}
        </span>
        {(issue.agentName || issue.agentId) ? (
          <span className="chip py-0.5">{issue.agentName || issue.agentId}</span>
        ) : null}
        {issue.category ? <span className="chip py-0.5">{issue.category}</span> : null}
        {typeof issue.confidence === 'number' ? (
          <span className="chip py-0.5">{Math.round(issue.confidence * 100)}% conf</span>
        ) : null}
        <span className="ml-auto flex items-center gap-1 font-mono text-[11px] text-mist-500">
          <MapPin className="h-3 w-3" />
          {line ? `line ${line}${issue.endLine && issue.endLine !== line ? `-${issue.endLine}` : ''}` : issue.file || ''}
        </span>
      </div>

      <h3 className="mt-3 text-sm font-semibold text-mist-100">{issue.title}</h3>
      {issue.description ? (
        <p className="mt-1.5 text-sm leading-relaxed text-mist-400">{issue.description}</p>
      ) : null}

      {suggestion ? (
        <div className="mt-3 rounded-lg border border-ink-700/80 bg-ink-950/50 p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold tracking-wider text-mist-500 uppercase">
            <Wrench className="h-3 w-3" aria-hidden="true" />
            Suggested fix
          </p>
          <p className="mt-1 text-xs leading-relaxed text-mist-300 whitespace-pre-wrap">{suggestion}</p>
        </div>
      ) : null}

      {(issue.hasDiff || issue.diff) && onFixDecision ? (
        <div className="mt-3 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onFixDecision('accepted')}
            className="btn btn-primary text-xs py-1 px-2.5"
          >
            <Check className="h-3 w-3" />
            Accept Fix
          </button>
          <button
            onClick={() => onFixDecision('rejected')}
            className="btn btn-secondary text-xs py-1 px-2.5"
          >
            <XCircle className="h-3 w-3" />
            Reject
          </button>
          <span className="ml-auto text-[10px] text-mist-500 flex items-center gap-1">
            <GitCompare className="h-3 w-3" />
            Has diff
          </span>
        </div>
      ) : null}
    </article>
  )
}
