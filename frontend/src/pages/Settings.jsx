import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Info,
  LogOut,
  RefreshCw,
  RotateCcw,
  Server,
  Settings2,
  SlidersHorizontal,
  User,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import LanguageSelector from '../components/LanguageSelector.jsx'
import { useReviews } from '../context/ReviewContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE_URL, getHealth } from '../lib/api.js'
import { cn } from '../lib/cn.js'
import { formatNumber } from '../lib/format.js'

function Section({ icon: Icon, title, description, children }) {
  return (
    <section className="card p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-ink-700 bg-ink-800/70 text-mist-300">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-sm font-semibold text-white">{title}</h2>
          <p className="mt-1 text-xs text-mist-500">{description}</p>
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}

function Toggle({ id, label, description, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <label htmlFor={id} className="text-sm font-medium text-mist-100">
          {label}
        </label>
        <p className="mt-0.5 text-xs text-mist-500">{description}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-6 w-11 shrink-0 rounded-full border transition-colors duration-150',
          checked ? 'border-brand-500 bg-brand-500' : 'border-ink-600 bg-ink-800',
        )}
      >
        <span
          className={cn(
            'absolute top-1 left-1 h-4 w-4 rounded-full bg-white transition-transform duration-150',
            checked ? 'translate-x-5' : 'translate-x-0',
          )}
          aria-hidden="true"
        />
      </button>
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex flex-col gap-1 border-b border-ink-700/60 py-3 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-xs text-mist-400">{label}</span>
      <span className="font-mono text-[11px] break-all text-mist-200">{value}</span>
    </div>
  )
}

const INITIAL_HEALTH = { status: 'idle', data: null, error: '' }

export default function Settings() {
  const { settings, updateSettings, resetSettings, reviews, historyState, refreshReviews } =
    useReviews()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [health, setHealth] = useState(INITIAL_HEALTH)

  const appName = import.meta.env.VITE_APP_NAME || 'ALPHA CodeGuard AI'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  async function checkConnection() {
    setHealth({ status: 'loading', data: null, error: '' })
    try {
      const data = await getHealth()
      setHealth({ status: 'ok', data, error: '' })
    } catch (error) {
      setHealth({ status: 'error', data: null, error: error.message })
    }
  }

  const connectionLabel =
    historyState === 'ready' ? 'Connected' : historyState === 'error' ? 'Unreachable' : 'Checking…'

  const getInitials = (name) => {
    if (!name) return 'U'
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A'
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    } catch {
      return dateString
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Settings
          </h1>
          <p className="mt-1.5 text-sm text-mist-400">
            Account, editor defaults, API connection, and environment details.
          </p>
        </div>
        <span className="chip w-fit">
          <CheckCircle2 className="h-3 w-3 text-emerald-400" aria-hidden="true" />
          Preferences saved in this browser
        </span>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <Section
            icon={User}
            title="Account"
            description="Your profile information and authentication details."
          >
            <div className="flex items-center gap-4 mb-4">
              {user?.profile_picture ? (
                <img
                  src={user.profile_picture}
                  alt={user.full_name}
                  className="h-16 w-16 rounded-full border border-ink-600"
                />
              ) : (
                <span
                  className="flex h-16 w-16 items-center justify-center rounded-full border border-ink-600 bg-gradient-to-br from-brand-500/30 to-aqua-500/20 text-lg font-semibold text-white"
                >
                  {getInitials(user?.full_name)}
                </span>
              )}
              <div>
                <p className="text-lg font-semibold text-white">{user?.full_name}</p>
                <p className="text-sm text-mist-400">{user?.email}</p>
              </div>
            </div>
            <InfoRow label="Profile name" value={user?.full_name || 'N/A'} />
            <InfoRow label="Email address" value={user?.email || 'N/A'} />
            <InfoRow label="Authentication provider" value={user?.provider || 'email'} />
            <InfoRow label="Account created" value={formatDate(user?.created_at)} />
            <div className="mt-4 pt-4 border-t border-ink-700/70">
              <button onClick={handleLogout} className="btn btn-danger w-full sm:w-auto">
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </div>
          </Section>

          <Section
            icon={SlidersHorizontal}
            title="Editor preferences"
            description="Applied to the review workspace on this device."
          >
            <LanguageSelector
              value={settings.defaultLanguage}
              onChange={(value) => updateSettings({ defaultLanguage: value })}
              label="Default language"
              id="default-language"
              className="max-w-xs"
            />

            <div className="mt-5">
              <label htmlFor="editor-font-size" className="label">
                Editor font size
              </label>
              <select
                id="editor-font-size"
                value={settings.editorFontSize}
                onChange={(event) =>
                  updateSettings({ editorFontSize: Number(event.target.value) })
                }
                className="field max-w-xs"
              >
                {[12, 13, 14, 15, 16].map((size) => (
                  <option key={size} value={size}>
                    {size} px
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-5">
              <Toggle
                id="word-wrap"
                label="Word wrap"
                description="Wrap long lines instead of scrolling horizontally."
                checked={settings.wordWrap}
                onChange={(value) => updateSettings({ wordWrap: value })}
              />
            </div>

            <div className="mt-5 flex justify-end border-t border-ink-700/70 pt-4">
              <button type="button" onClick={resetSettings} className="btn btn-ghost text-xs">
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Reset preferences
              </button>
            </div>
          </Section>

          <Section
            icon={Database}
            title="Review data"
            description="History is stored by the FastAPI backend in SQLite."
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-mist-400">
                <span className="font-semibold text-mist-100">{formatNumber(reviews.length)}</span>{' '}
                {reviews.length === 1 ? 'review' : 'reviews'} loaded ·{' '}
                <span
                  className={cn(
                    historyState === 'ready'
                      ? 'text-emerald-300'
                      : historyState === 'error'
                        ? 'text-rose-300'
                        : 'text-mist-400',
                  )}
                >
                  {connectionLabel}
                </span>
              </p>
              <button
                type="button"
                onClick={() => void refreshReviews()}
                className="btn btn-secondary text-xs"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Refresh history
              </button>
            </div>
            <p className="mt-4 border-t border-ink-700/70 pt-3 text-[11px] leading-relaxed text-mist-500">
              Reviews are persisted server-side. Removing individual reviews is not available in this
              phase.
            </p>
          </Section>
        </div>

        <div className="space-y-4">
          <Section
            icon={Server}
            title="API connection"
            description="The frontend talks to the FastAPI backend through VITE_API_BASE_URL."
          >
            <InfoRow label="API base URL" value={API_BASE_URL} />
            <InfoRow label="Connection" value={connectionLabel} />

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void checkConnection()}
                disabled={health.status === 'loading'}
                className="btn btn-secondary text-xs"
              >
                {health.status === 'loading' ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Server className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                Test connection
              </button>
              {health.status === 'ok' ? (
                <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-300">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {health.data?.service} v{health.data?.version} · database{' '}
                  {health.data?.database} · AI {health.data?.llm?.status}
                </span>
              ) : null}
              {health.status === 'error' ? (
                <span className="inline-flex items-start gap-1.5 text-[11px] text-rose-300">
                  <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {health.error}
                </span>
              ) : null}
            </div>

            <p className="mt-4 text-[11px] leading-relaxed text-mist-500">
              Configure the backend URL in <code className="text-mist-300">.env.local</code> and
              restart the dev server. Start the API with{' '}
              <code className="text-mist-300">uvicorn app.main:app --reload</code> from{' '}
              <code className="text-mist-300">backend/</code>.
            </p>
          </Section>

          <Section
            icon={Settings2}
            title="Environment"
            description="Read-only values resolved at build time."
          >
            <InfoRow label="App name" value={appName} />
            <InfoRow label="Interface" value="React + Vite + Tailwind" />
            <InfoRow label="Backend" value="FastAPI + SQLAlchemy + SQLite" />
            <InfoRow
              label="AI engine"
              value={
                health.status === 'ok'
                  ? `${health.data?.llm?.provider ?? 'unknown'} · ${health.data?.llm?.status ?? 'unknown'}`
                  : 'Use “Test connection” to check'
              }
            />
          </Section>

          <Section
            icon={Info}
            title="About this build"
            description="Phase 2 — backend and frontend integration."
          >
            <p className="text-xs leading-relaxed text-mist-400">
              ALPHA CodeGuard AI is a multi-agent code review workspace built by Team ALPHA. Reviews
              are stored by the FastAPI backend per account. Findings come from the review agents or a
              static analyzer; nothing is fabricated, and submitted code is never executed.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="chip">React 19</span>
              <span className="chip">FastAPI</span>
              <span className="chip">SQLAlchemy</span>
              <span className="chip">SQLite</span>
              <span className="chip">Monaco Editor</span>
            </div>
          </Section>
        </div>
      </div>
    </div>
  )
}
