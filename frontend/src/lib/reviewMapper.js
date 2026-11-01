/**
 * Maps the backend review payload (snake_case) to the shape used by the UI.
 */
export function mapReview(payload) {
  if (!payload) return null

  const agents = (payload.agents ?? []).map((agent) => ({
    id: agent.id,
    name: agent.name,
    status: agent.status ?? 'pending',
    findings: agent.findings ?? 0,
    durationMs: agent.duration_ms ?? null,
  }))

  return {
    id: payload.id,
    status: payload.status ?? 'pending',
    createdAt: payload.created_at,
    language: payload.language,
    languageLabel: payload.language_label ?? payload.language,
    filename: payload.filename ?? null,
    code: payload.code ?? '',
    lines: payload.lines ?? 0,
    characters: payload.characters ?? 0,
    score: typeof payload.quality_score === 'number' ? payload.quality_score : null,
    grade: payload.grade ?? null,
    summary: payload.summary ?? null,
    issues: (payload.issues ?? []).map((issue) => ({
      id: issue.id,
      agentId: issue.agent_id,
      agentName: issue.agent_name,
      severity: issue.severity,
      title: issue.title,
      description: issue.description,
      suggestion: issue.suggestion,
      line: issue.line,
    })),
    agents,
    counts: {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      total: 0,
      ...(payload.counts ?? {}),
    },
    durationMs: payload.duration_ms ?? null,
    isDemo: false,
  }
}

export function isPendingReview(review) {
  return (review?.status ?? 'pending') === 'pending'
}
