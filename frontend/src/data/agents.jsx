import { Bug, Gauge, ShieldAlert, Sparkles, Wrench } from 'lucide-react'

/**
 * The five review agents that make up the CodeGuard pipeline.
 * The backend registers these agents; findings stay pending until AI analysis
 * is configured (see backend/app/analyzers/pipeline.py).
 */
export const AGENTS = [
  {
    id: 'bug',
    name: 'Bug Detection Agent',
    shortName: 'Bugs',
    description: 'Traces logic errors, edge cases, and unhandled runtime exceptions.',
    icon: Bug,
    tone: {
      icon: 'border-rose-500/20 bg-rose-500/10 text-rose-300',
      bar: 'bg-rose-400',
      text: 'text-rose-400',
      glow: 'from-rose-500/15',
    },
  },
  {
    id: 'security',
    name: 'Security Analysis Agent',
    shortName: 'Security',
    description: 'Checks injection paths, leaked secrets, and missing authorization.',
    icon: ShieldAlert,
    tone: {
      icon: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
      bar: 'bg-amber-400',
      text: 'text-amber-400',
      glow: 'from-amber-500/15',
    },
  },
  {
    id: 'performance',
    name: 'Performance Optimization Agent',
    shortName: 'Performance',
    description: 'Finds hot-path allocations, redundant I/O, and unbounded growth.',
    icon: Gauge,
    tone: {
      icon: 'border-sky-500/20 bg-sky-500/10 text-sky-300',
      bar: 'bg-sky-400',
      text: 'text-sky-400',
      glow: 'from-sky-500/15',
    },
  },
  {
    id: 'quality',
    name: 'Code Quality Agent',
    shortName: 'Quality',
    description: 'Reviews readability, duplication, naming, and module structure.',
    icon: Sparkles,
    tone: {
      icon: 'border-violet-500/20 bg-violet-500/10 text-violet-300',
      bar: 'bg-violet-400',
      text: 'text-violet-400',
      glow: 'from-violet-500/15',
    },
  },
  {
    id: 'fix',
    name: 'Fix & Validation Agent',
    shortName: 'Fix',
    description: 'Drafts a fix for each reported issue and validates the patch.',
    icon: Wrench,
    tone: {
      icon: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
      bar: 'bg-emerald-400',
      text: 'text-emerald-400',
      glow: 'from-emerald-500/15',
    },
  },
]

export function getAgent(id) {
  return AGENTS.find((agent) => agent.id === id)
}
