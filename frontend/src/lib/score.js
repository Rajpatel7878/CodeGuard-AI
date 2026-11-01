export function scoreClasses(score) {
  if (typeof score !== 'number') return 'border-ink-600 bg-ink-800 text-mist-300'
  if (score >= 85) return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (score >= 70) return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-rose-500/30 bg-rose-500/10 text-rose-300'
}

export function scoreDescriptor(score) {
  if (typeof score !== 'number') return 'No score yet'
  if (score >= 90) return 'Excellent'
  if (score >= 80) return 'Strong'
  if (score >= 70) return 'Acceptable'
  if (score >= 60) return 'Needs work'
  return 'At risk'
}
