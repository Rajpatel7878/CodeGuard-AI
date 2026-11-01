import { ChevronRight, Menu, Settings, ShieldCheck } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useReviews } from '../context/ReviewContext.jsx'
import { cn } from '../lib/cn.js'
import { getPageTitle } from '../lib/navigation.jsx'

const APP_NAME = import.meta.env.VITE_APP_NAME || 'ALPHA CodeGuard AI'

export default function Navbar({ onOpenSidebar }) {
  const { pathname } = useLocation()
  const { apiAvailable } = useReviews()
  const pageTitle = getPageTitle(pathname)

  return (
    <header className="sticky top-0 z-30 border-b border-ink-700/80 bg-ink-950/85 backdrop-blur-md">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Open navigation"
          className="btn btn-ghost -ml-2 p-2 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link to="/" className="flex items-center gap-2.5 lg:hidden">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/30 bg-brand-500/10">
            <ShieldCheck className="h-4 w-4 text-brand-300" />
          </span>
          <span className="text-sm font-semibold text-white">CodeGuard AI</span>
        </Link>

        <div className="hidden min-w-0 flex-1 items-center gap-2 text-sm lg:flex">
          <span className="text-mist-500">Workspace</span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-500" aria-hidden="true" />
          <span className="truncate font-medium text-mist-200">{pageTitle}</span>
        </div>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <span
            className={cn(
              'hidden items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium sm:inline-flex',
              apiAvailable
                ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                : 'border-rose-500/25 bg-rose-500/10 text-rose-300',
            )}
            title={
              apiAvailable
                ? 'Connected to the FastAPI review backend.'
                : 'The FastAPI review backend is unreachable.'
            }
          >
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                apiAvailable ? 'bg-emerald-400' : 'bg-rose-400',
              )}
              aria-hidden="true"
            />
            {apiAvailable ? 'API connected' : 'API offline'}
          </span>

          <Link
            to="/settings"
            aria-label="Settings"
            className="btn btn-ghost p-2"
            title="Settings"
          >
            <Settings className="h-4.5 w-4.5" />
          </Link>

          <div className="flex items-center gap-2.5 border-l border-ink-700/80 pl-2.5 sm:pl-3.5">
            <span
              className="flex h-8 w-8 items-center justify-center rounded-full border border-ink-600 bg-gradient-to-br from-brand-500/30 to-aqua-500/20 text-[11px] font-semibold text-white"
              aria-hidden="true"
            >
              AL
            </span>
            <div className="hidden leading-tight sm:block">
              <p className="text-xs font-medium text-mist-200">Team ALPHA</p>
              <p className="text-[11px] text-mist-500">{APP_NAME}</p>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
