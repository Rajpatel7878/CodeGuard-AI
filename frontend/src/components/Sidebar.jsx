import { Sparkles, ShieldCheck, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '../lib/cn.js'
import { NAV_ITEMS } from '../lib/navigation.jsx'

export default function Sidebar({ open, onClose }) {
  return (
    <aside
      id="app-sidebar"
      aria-label="Workspace navigation"
      className={cn(
        'fixed inset-y-0 left-0 z-50 flex w-72 shrink-0 flex-col border-r border-ink-700/80 bg-ink-900/95 backdrop-blur-md transition-transform duration-200 ease-out',
        'lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:translate-x-0 lg:bg-ink-900/50 xl:w-72',
        open ? 'translate-x-0' : '-translate-x-full',
      )}
    >
      <div className="flex h-16 items-center justify-between border-b border-ink-700/70 px-4">
        <NavLink to="/" onClick={onClose} className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-brand-500/30 bg-gradient-to-br from-brand-500/25 to-aqua-500/10 shadow-lg shadow-brand-600/10">
            <ShieldCheck className="h-5 w-5 text-brand-300" />
          </span>
          <span className="min-w-0 leading-tight">
            <span className="flex items-center gap-1.5">
              <span className="text-[10px] font-bold tracking-[0.2em] text-aqua-400">ALPHA</span>
            </span>
            <span className="block truncate text-sm font-semibold text-white">CodeGuard AI</span>
          </span>
        </NavLink>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="btn btn-ghost -mr-1.5 p-1.5 lg:hidden"
        >
          <X className="h-4.5 w-4.5" />
        </button>
      </div>

      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-5">
        <p className="eyebrow px-3 pb-2.5">Workspace</p>
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150',
                    isActive
                      ? 'bg-brand-500/10 text-white ring-1 ring-brand-500/20 ring-inset'
                      : 'text-mist-300 hover:bg-ink-800/80 hover:text-white',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon
                      className={cn(
                        'h-4.5 w-4.5 shrink-0 transition-colors',
                        isActive ? 'text-brand-300' : 'text-mist-500 group-hover:text-mist-300',
                      )}
                      aria-hidden="true"
                    />
                    <span className="truncate">{item.label}</span>
                    {isActive ? (
                      <span
                        className="ml-auto h-1.5 w-1.5 rounded-full bg-aqua-400"
                        aria-hidden="true"
                      />
                    ) : null}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-ink-700/70 p-3">
        <div className="rounded-xl border border-ink-700/80 bg-ink-850/80 p-3.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-mist-200">
            <Sparkles className="h-3.5 w-3.5 text-brand-300" aria-hidden="true" />
            Phase 2 · Backend
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-mist-500">
            Reviews are stored by the FastAPI API. AI findings stay pending until configured.
          </p>
        </div>
        <p className="mt-3 px-1 text-[11px] text-mist-500">Built by Team ALPHA</p>
      </div>
    </aside>
  )
}
