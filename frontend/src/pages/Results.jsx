/**
 * Detailed code review results page displaying AI agent findings,
 * quality scores, metrics breakdown, and interactive code diffs.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Clock,
  Code2,
  FileSearch,
  Filter,
  GitCompare,
  Plus,
  ShieldAlert,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react'
import AgentCard from '../components/AgentCard.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import EmptyState from '../components/EmptyState.jsx'
import ErrorState from '../components/ErrorState.jsx'
import IssueCard from '../components/IssueCard.jsx'
import LoadingIndicator from '../components/LoadingIndicator.jsx'
import ScoreCard from '../components/ScoreCard.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { useReviews } from '../context/ReviewContext.jsx'
import { AGENTS } from '../data/agents.jsx'
import { cn } from '../lib/cn.js'
import { formatDateTime, formatDuration, formatNumber } from '../lib/format.js'
import { getLanguage } from '../lib/languages.js'
import { scoreDescriptor } from '../lib/score.js'
import { SEVERITIES, SEVERITY_ORDER } from '../lib/severity.js'

const SEVERITY_WEIGHT = { critical: 4, high: 3, medium: 2, low: 1, info: 0 }

export default function Results() {
  const { reviewId } = useParams()
  const location = useLocation()
  const { reviews, historyState, historyError, refreshReviews, setFixDecision, fetchReview } = useReviews()
  const [severityByReview, setSeverityByReview] = useState({})
  const [selectedIssueId, setSelectedIssueId] = useState(null)
  const [filterSeverity, setFilterSeverity] = useState('all')
  const [filterCategory, setFilterCategory] = useState('all')
  const [filterAgent, setFilterAgent] = useState('all')
  const [filterFile, setFilterFile] = useState('all')
  const [sortBy, setSortBy] = useState('severity')
  const [showFilters, setShowFilters] = useState(false)
  const editorRef = useRef(null)

  const review = reviewId ? reviews.find((item) => item.id === reviewId) : reviews[0]

  const counts = useMemo(
    () => ({
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
      total: 0,
      ...(review?.counts ?? {}),
    }),
    [review?.counts],
  )

  useEffect(() => {
    if (reviewId && !review && historyState !== 'loading') {
      // A missing review is rendered as an empty state, not an unhandled rejection.
      fetchReview(reviewId).catch(() => {})
    }
  }, [reviewId, review, historyState, fetchReview])

  const activeSeverity = review ? (severityByReview[review.id] ?? 'all') : 'all'
  const issues = useMemo(() => review?.issues ?? [], [review])
  const agents = review?.agents ?? []
  const completedAgents = agents.filter((agent) => agent.status === 'complete' || agent.status === 'completed').length
  const pending = review?.status === 'pending'
  const extension = review ? getLanguage(review.language).extension : 'txt'

  const categories = useMemo(() => {
    const cats = new Set()
    issues.forEach((issue) => { if (issue.category) cats.add(issue.category) })
    return Array.from(cats)
  }, [issues])

  const agentOptions = useMemo(() => {
    const set = new Set()
    issues.forEach((issue) => { if (issue.agentName || issue.agentId) set.add(issue.agentName || issue.agentId) })
    return Array.from(set)
  }, [issues])

  const fileOptions = useMemo(() => {
    const set = new Set()
    issues.forEach((issue) => { if (issue.file) set.add(issue.file) })
    if (review?.filename) set.add(review.filename)
    return Array.from(set)
  }, [issues, review?.filename])

  const filteredAndSortedIssues = useMemo(() => {
    let result = issues.filter((issue) => {
      if (activeSeverity !== 'all' && issue.severity?.toLowerCase() !== activeSeverity) return false
      if (filterSeverity !== 'all' && issue.severity?.toLowerCase() !== filterSeverity) return false
      if (filterCategory !== 'all' && issue.category !== filterCategory) return false
      if (filterAgent !== 'all') {
        const agentLabel = issue.agentName || issue.agentId
        if (agentLabel !== filterAgent) return false
      }
      if (filterFile !== 'all') {
        if (issue.file === filterFile || review?.filename === filterFile) {
          // ok
        } else {
          return false
        }
      }
      return true
    })

    result = [...result].sort((a, b) => {
      if (sortBy === 'severity') {
        const wa = SEVERITY_WEIGHT[a.severity?.toLowerCase()] ?? 0
        const wb = SEVERITY_WEIGHT[b.severity?.toLowerCase()] ?? 0
        if (wb !== wa) return wb - wa
      } else if (sortBy === 'line') {
        return (a.line || a.startLine || 0) - (b.line || b.startLine || 0)
      } else if (sortBy === 'agent') {
        return (a.agentName || '').localeCompare(b.agentName || '')
      }
      return 0
    })
    return result
  }, [
    issues,
    activeSeverity,
    filterSeverity,
    filterCategory,
    filterAgent,
    filterFile,
    sortBy,
    review?.filename,
  ])

  if (!review && historyState === 'loading') {
    return (
      <div className="card">
        <LoadingIndicator label="Loading review" description="Fetching the stored review from the API." className="py-24" />
      </div>
    )
  }

  if (!review && historyState === 'error') {
    return (
      <div className="card">
        <ErrorState title="Could not load this review" message={historyError} onRetry={() => void refreshReviews()} />
      </div>
    )
  }

  if (!review) {
    return (
      <div className="card">
        <EmptyState
          icon={FileSearch}
          title={reviewId ? 'Review not found' : 'No reviews yet'}
          description={reviewId ? 'This review is not stored in the API.' : 'Submit a snippet to create your first review record.'}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link to="/history" className="btn btn-secondary">Review history</Link>
              <Link to="/review" className="btn btn-primary"><Plus className="h-4 w-4" aria-hidden="true" />New review</Link>
            </div>
          }
        />
      </div>
    )
  }

  const filteredIssues = filteredAndSortedIssues

  const handleEditorMount = (editor) => { editorRef.current = editor }

  const handleIssueClick = (issue) => {
    setSelectedIssueId(issue.id)
    const line = issue.line || issue.startLine
    if (editorRef.current && line) {
      editorRef.current.revealLineInCenter(line)
      editorRef.current.setPosition({ lineNumber: line, column: 1 })
      editorRef.current.focus()
    }
  }

  const handleFixDecision = async (issue, decision) => {
    if (!reviewId) return
    try { await setFixDecision({ reviewId, findingId: issue.id, decision }) } catch (e) { console.error(e) }
  }

  const tabs = [{ key: 'all', label: 'All', count: issues.length }, ...SEVERITY_ORDER.map((key) => ({ key, label: SEVERITIES[key].label, count: counts[key] ?? 0 }))]
  const selectedIssue = selectedIssueId ? issues.find((i) => i.id === selectedIssueId) : null

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link to="/history" className="inline-flex items-center gap-1.5 text-xs font-medium text-mist-400 transition-colors hover:text-mist-200"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />Review history</Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Review results</h1>
          <p className="mt-1.5 text-sm text-mist-400">{review.filename ? review.filename + ' · ' : ''}{review.languageLabel} · {formatNumber(review.lines)} lines · {formatDateTime(review.createdAt)}{review.durationMs ? ' · ' + formatDuration(review.durationMs) : ''}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={review.status} />
          <Link to="/review" className="btn btn-secondary text-xs"><Code2 className="h-3.5 w-3.5" aria-hidden="true" />New review</Link>
        </div>
      </div>
      {location.state?.justCreated && review.status === 'completed' ? (<div role="status" className="mt-5 flex items-start gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs leading-relaxed text-emerald-200"><CheckCircle2 className="mt-px h-4 w-4 shrink-0" aria-hidden="true" /><p>Review complete. Results below come from the stored analysis.</p></div>) : null}
      {location.state?.justCreated && review.status === 'completed_with_errors' ? (<div role="status" className="mt-5 flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-200"><ShieldAlert className="mt-px h-4 w-4 shrink-0" aria-hidden="true" /><p>Review finished with errors. Some agents did not complete — see the agent breakdown.</p></div>) : null}
      {review.status === 'error' ? (<div role="alert" className="mt-5 flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs leading-relaxed text-rose-200"><XCircle className="mt-px h-4 w-4 shrink-0" aria-hidden="true" /><p>{review.summary ?? 'The review could not be completed.'}</p></div>) : null}
      {pending ? (<div role="status" className="mt-4 flex items-start gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 text-xs leading-relaxed text-mist-300"><Clock className="mt-px h-4 w-4 shrink-0 text-amber-300" aria-hidden="true" /><p>{review.summary ?? 'Analysis in progress.'}</p></div>) : null}
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <ScoreCard label="Quality score" value={review.score ?? '—'} suffix={review.score === null ? undefined : '/100'} hint={review.score === null ? 'Awaiting analysis' : review.grade + ' · ' + scoreDescriptor(review.score)} icon={ShieldCheck} tone="emerald" progress={review.score ?? 0} />
        <ScoreCard label="Total findings" value={formatNumber(counts.total ?? 0)} hint="Across all agents." icon={FileSearch} tone="brand" />
        <ScoreCard label="Critical" value={formatNumber(counts.critical ?? 0)} hint="Fix before shipping." icon={ShieldAlert} tone="rose" />
        <ScoreCard label="High" value={formatNumber(counts.high ?? 0)} hint="Should fix soon." icon={ShieldAlert} tone="orange" />
        <ScoreCard label="Agents completed" value={completedAgents + '/' + (agents.length || 5)} hint={review.durationMs ? 'Total: ' + formatDuration(review.durationMs) : 'Pipeline run'} icon={CheckCircle2} tone="sky" />
      </div>
      <div className="mt-6 grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="card overflow-hidden">
          <header className="border-b border-ink-700/80 p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white">Findings<span className="chip tabular-nums">{filteredIssues.length}</span></h2>
              <button type="button" onClick={() => setShowFilters(!showFilters)} className="btn btn-ghost text-xs"><Filter className="h-3.5 w-3.5" aria-hidden="true" />Filters & Sort</button>
            </div>
            {showFilters ? (
              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
                <select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)} className="field text-xs"><option value="all">All Severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option><option value="info">Info</option></select>
                <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} className="field text-xs"><option value="all">All Categories</option>{categories.map((cat) => <option key={cat} value={cat}>{cat}</option>)}</select>
                <select value={filterAgent} onChange={(e) => setFilterAgent(e.target.value)} className="field text-xs"><option value="all">All Agents</option>{agentOptions.map((agent) => <option key={agent} value={agent}>{agent}</option>)}</select>
                <select value={filterFile} onChange={(e) => setFilterFile(e.target.value)} className="field text-xs"><option value="all">All Files</option>{fileOptions.map((file) => <option key={file} value={file}>{file}</option>)}</select>
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="field text-xs"><option value="severity">Sort by Severity</option><option value="line">Sort by Line</option><option value="agent">Sort by Agent</option></select>
              </div>
            ) : null}
            {issues.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {tabs.map((tab) => (
                  <button key={tab.key} type="button" onClick={() => setSeverityByReview((previous) => ({ ...previous, [review.id]: tab.key }))} aria-pressed={activeSeverity === tab.key} className={cn('rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors', activeSeverity === tab.key ? 'border-brand-500/40 bg-brand-500/15 text-white' : 'border-ink-700 bg-ink-800/50 text-mist-400 hover:border-ink-600 hover:text-mist-200')}>
                    {tab.label}<span className="ml-1.5 tabular-nums opacity-70">{tab.count}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </header>
          <div className="space-y-3 p-4 sm:p-5">
            {filteredIssues.length > 0 ? (
              filteredIssues.map((issue) => <IssueCard key={issue.id} issue={issue} onClick={() => handleIssueClick(issue)} isSelected={selectedIssueId === issue.id} onFixDecision={(decision) => handleFixDecision(issue, decision)} reviewId={review.id} />)
            ) : (
              <EmptyState icon={pending ? Clock : CheckCircle2} title={pending ? 'Analysis pending' : 'No findings reported'} description={pending ? 'This review is stored, but analysis may still be in progress.' : issues.length === 0 ? 'No findings have been generated.' : 'No findings match the current filters.'} className="py-10" />
            )}
          </div>
        </section>
        <aside className="space-y-4 xl:sticky xl:top-24">
          <section className="card p-5">
            <h2 className="text-sm font-semibold text-white">Issue mix</h2>
            <ul className="mt-4 space-y-3">
              {SEVERITY_ORDER.map((key) => {
                const severity = SEVERITIES[key]
                const count = counts[key] ?? 0
                const percentage = counts.total ? Math.round((count / counts.total) * 100) : 0
                return (
                  <li key={key}>
                    <div className="flex items-center justify-between text-[11px]"><span className="flex items-center gap-1.5 text-mist-300"><span className={cn('h-1.5 w-1.5 rounded-full', severity.dot)} aria-hidden="true" />{severity.label}</span><span className="tabular-nums text-mist-500">{count}</span></div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-800"><div className={cn('h-full rounded-full', severity.bar)} style={{ width: percentage + '%' }} /></div>
                  </li>
                )
              })}
            </ul>
            {counts.total === 0 ? <p className="mt-3 text-[11px] text-mist-500">No findings have been generated.</p> : null}
          </section>
          <section className="space-y-2.5">
            <h2 className="px-1 text-sm font-semibold text-white">Agent breakdown</h2>
            {AGENTS.map((agentDef) => {
              const entry = agents.find(
                (item) =>
                  item.id === agentDef.id ||
                  item.agentId === agentDef.id ||
                  item.name === agentDef.name ||
                  item.agentName === agentDef.name,
              )
              if (!entry) {
                return (
                  <AgentCard
                    key={agentDef.id}
                    agent={agentDef}
                    status="not reported"
                    findings={0}
                    durationMs={null}
                  />
                )
              }
              return (
                <AgentCard
                  key={entry.id || entry.agentId || agentDef.id}
                  agent={AGENTS.find((item) => item.id === (entry.id || entry.agentId)) || agentDef}
                  status={entry.status}
                  findings={entry.findings ?? 0}
                  durationMs={entry.durationMs}
                  summary={entry.summary}
                  errorMessage={entry.errorMessage || entry.error_message}
                />
              )
            })}
          </section>
          {selectedIssue && (selectedIssue.hasDiff || selectedIssue.diff) ? (
            <section className="card overflow-hidden">
              <header className="flex items-center justify-between gap-3 border-b border-ink-700/80 px-4 py-3"><h2 className="flex items-center gap-2 text-sm font-semibold text-white"><GitCompare className="h-4 w-4" />Fix Comparison</h2><button onClick={() => setSelectedIssueId(null)} className="btn btn-ghost p-1"><X className="h-3.5 w-3.5" /></button></header>
              <div className="p-4 space-y-3">
                {selectedIssue.validationStatus ? <div className="text-xs"><span className="text-mist-400">Validation: </span><span className={cn(selectedIssue.validationStatus === 'Passed' ? 'text-emerald-400' : selectedIssue.validationStatus === 'Failed' ? 'text-rose-400' : 'text-amber-400')}>{selectedIssue.validationStatus}</span>{selectedIssue.validationDetails ? <p className="mt-1 text-mist-500">{selectedIssue.validationDetails}</p> : null}</div> : null}
                {selectedIssue.diff ? <div><p className="text-[10px] font-semibold tracking-wider text-mist-500 uppercase mb-2">Unified Diff</p><pre className="max-h-60 overflow-auto p-2 bg-ink-950/70 rounded text-[10px] leading-relaxed text-mist-300 font-mono">{selectedIssue.diff}</pre></div> : null}
                <div className="flex gap-2">
                  <button onClick={() => handleFixDecision(selectedIssue, 'accepted')} className="btn btn-primary flex-1 text-xs py-1.5"><Check className="h-3.5 w-3.5" />Accept</button>
                  <button onClick={() => handleFixDecision(selectedIssue, 'rejected')} className="btn btn-secondary flex-1 text-xs py-1.5"><XCircle className="h-3.5 w-3.5" />Reject</button>
                </div>
                {review.fixDecisions?.[selectedIssue.id] ? <p className="text-[10px] text-mist-500 text-center">Decision: {review.fixDecisions[selectedIssue.id]}</p> : null}
              </div>
            </section>
          ) : null}
          <section className="card overflow-hidden">
            <div className="flex items-center justify-between gap-3 border-b border-ink-700/80 px-4 py-3"><h2 className="text-sm font-semibold text-white">Code snapshot</h2><span className="max-w-[9rem] truncate font-mono text-[10px] text-mist-500">{review.filename ?? 'snippet.' + extension}</span></div>
            <div className="h-72"><CodeEditor value={review.code} onChange={() => {}} language={getLanguage(review.language).monaco} readOnly={true} height="100%" onMount={handleEditorMount} /></div>
          </section>
        </aside>
      </div>
    </div>
  )
}
