import { ArrowLeft, Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="card flex flex-col items-center justify-center px-6 py-20 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-ink-700 bg-ink-800/80">
        <Compass className="h-5 w-5 text-mist-400" aria-hidden="true" />
      </span>
      <p className="mt-5 font-mono text-xs tracking-widest text-mist-500">404</p>
      <h1 className="mt-2 text-xl font-semibold text-white">This page does not exist</h1>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-400">
        The route you opened is not part of the CodeGuard workspace.
      </p>
      <Link to="/" className="btn btn-primary mt-6">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to dashboard
      </Link>
    </div>
  )
}
