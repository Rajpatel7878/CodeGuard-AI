import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Clock, Info, Loader2, RotateCcw, Sparkles } from 'lucide-react'
import AgentCard from '../components/AgentCard.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import LanguageSelector from '../components/LanguageSelector.jsx'
import LoadingIndicator from '../components/LoadingIndicator.jsx'
import UploadCode from '../components/UploadCode.jsx'
import { useReviews } from '../context/ReviewContext.jsx'
import { AGENTS } from '../data/agents.jsx'
import { getLanguage, languageFromFileName } from '../lib/languages.js'

const MAX_CODE_LENGTH = 200_000

function validateCode(code) {
  if (!code.trim()) return 'Add some code before running a review.'
  if (code.length > MAX_CODE_LENGTH) {
    return 'This snippet is too large. The API accepts up to 200,000 characters.'
  }
  return null
}

const initialAgentStatus = () =>
  Object.fromEntries(AGENTS.map((agent) => [agent.id, 'idle']))

export default function ReviewCode() {
  const navigate = useNavigate()
  const { createReview, settings } = useReviews()

  const [language, setLanguage] = useState(settings.defaultLanguage)
  const [code, setCode] = useState('')
  const [fileMeta, setFileMeta] = useState(null)
  const [error, setError] = useState('')
  const [runError, setRunError] = useState('')
  const [phase, setPhase] = useState('idle')
  const [agentStatus, setAgentStatus] = useState(initialAgentStatus)

  const running = phase === 'submitting'
  const activeLanguage = getLanguage(language)
  const lineCount = code ? code.split('\n').length : 0

  function handleFileLoad({ code: fileCode, fileName }) {
    setCode(fileCode)
    setFileMeta({ name: fileName })
    setError('')
    setRunError('')
    const detected = languageFromFileName(fileName)
    if (detected) setLanguage(detected)
  }

  function handleReset() {
    if (running) return
    setCode('')
    setFileMeta(null)
    setError('')
    setRunError('')
    setAgentStatus(initialAgentStatus())
  }

  async function handleRun() {
    if (running) return
    const validation = validateCode(code)
    if (validation) {
      setError(validation)
      setRunError('')
      return
    }

    setError('')
    setRunError('')
    setPhase('submitting')
    setAgentStatus(initialAgentStatus())

    try {
      const review = await createReview({
        code,
        language,
        filename: fileMeta?.name ?? null,
      })
      navigate(`/results/${review.id}`, { state: { justCreated: true } })
    } catch (submitError) {
      setPhase('idle')
      setAgentStatus(initialAgentStatus())
      setRunError(submitError.message || 'The review could not be submitted.')
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Review code
          </h1>
          <p className="mt-1.5 text-sm text-mist-400">
            Submit a snippet or file to the five-agent review pipeline.
          </p>
        </div>
        <span className="chip w-fit">
          <Clock className="h-3 w-3 text-amber-300" aria-hidden="true" />
          Five-agent pipeline
        </span>
      </div>

      <div className="mt-6 grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="card overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-ink-700/80 p-4 sm:flex-row sm:items-end sm:justify-between">
            <LanguageSelector
              value={language}
              onChange={setLanguage}
              disabled={running}
              className="sm:w-52"
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className="chip max-w-[12rem] truncate font-mono">
                {fileMeta?.name ?? `snippet.${activeLanguage.extension}`}
              </span>
              <button
                type="button"
                onClick={handleReset}
                disabled={running || (!code && !fileMeta)}
                className="btn btn-ghost px-2.5 py-1.5 text-xs"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Clear
              </button>
            </div>
          </div>

          <div className="border-b border-ink-700/60 bg-ink-950/40 p-3.5 sm:px-4">
            <UploadCode
              onFileLoad={handleFileLoad}
              onClear={() => {
                setFileMeta(null)
                setCode('')
              }}
              fileName={fileMeta?.name}
              disabled={running}
            />
          </div>

          {error ? (
            <div
              role="alert"
              className="mx-4 mt-4 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-xs leading-relaxed text-amber-200"
            >
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          ) : null}

          {runError ? (
            <div
              role="alert"
              className="mx-4 mt-4 flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2.5 text-xs leading-relaxed text-rose-200"
            >
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>{runError}</span>
            </div>
          ) : null}

          <div className="h-[360px] sm:h-[440px] xl:h-[520px]">
            <CodeEditor
              value={code}
              onChange={setCode}
              language={activeLanguage.monaco}
              languageId={language}
              fontSize={settings.editorFontSize}
              wordWrap={settings.wordWrap}
              minimap={settings.minimap}
              height="100%"
              title="Source Code"
            />
          </div>

          <div className="flex flex-col gap-3 border-t border-ink-700/80 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11px] text-mist-500">
              {lineCount} {lineCount === 1 ? 'line' : 'lines'} · {code.length} characters
            </p>
            <button
              type="button"
              onClick={handleRun}
              disabled={running}
              className="btn btn-primary w-full sm:w-auto"
            >
              {running ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              )}
              {running ? 'Submitting…' : 'Submit review'}
            </button>
          </div>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-24">
          <div className="card p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-white">Agent pipeline</h2>
                <p className="mt-1 text-xs text-mist-500">
                  Five agents are registered for every submission.
                </p>
              </div>
              <span className="chip shrink-0">{AGENTS.length} agents</span>
            </div>

            {running ? (
              <LoadingIndicator
                label="Submitting review"
                description="Running static analysis and the review agents."
                className="mt-4 rounded-lg border border-ink-700 bg-ink-950/40 py-4"
              />
            ) : null}

            <div className="mt-4 space-y-2.5">
              {AGENTS.map((agent) => (
                <AgentCard key={agent.id} agent={agent} status={agentStatus[agent.id]} />
              ))}
            </div>
          </div>

          <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-3.5 py-3 text-[11px] leading-relaxed text-mist-300">
            <Info className="mt-px h-3.5 w-3.5 shrink-0 text-amber-300" aria-hidden="true" />
            <p>
              Reviews are analysed statically and, when the backend has an AI provider key
              configured, by the five AI agents. The backend never executes your code.
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}
