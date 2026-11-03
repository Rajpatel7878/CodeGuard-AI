export const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low']

export const SEVERITIES = {
  critical: {
    label: 'Critical',
    badge: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
    dot: 'bg-rose-400',
    bar: 'bg-rose-400',
    text: 'text-rose-300',
    rail: 'border-l-rose-500/70',
  },
  high: {
    label: 'High',
    badge: 'border-orange-500/30 bg-orange-500/10 text-orange-300',
    dot: 'bg-orange-400',
    bar: 'bg-orange-400',
    text: 'text-orange-300',
    rail: 'border-l-orange-500/70',
  },
  medium: {
    label: 'Medium',
    badge: 'border-amber-500/25 bg-amber-500/10 text-amber-200',
    dot: 'bg-amber-400',
    bar: 'bg-amber-400',
    text: 'text-amber-200',
    rail: 'border-l-amber-500/60',
  },
  low: {
    label: 'Low',
    badge: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
    dot: 'bg-sky-400',
    bar: 'bg-sky-400',
    text: 'text-sky-300',
    rail: 'border-l-sky-500/60',
  },
}

export function getSeverity(key) {
  return SEVERITIES[key] ?? SEVERITIES.low
}
