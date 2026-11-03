/**
 * Maps the backend review payload (snake_case) to the shape used by the UI.
 */
export function mapReview(payload) {
  if (!payload) return null

  const agents = (payload.agents ?? []).map((agent) => ({
    id: agent.id ?? agent.agent_id,
    agentId: agent.agent_id ?? agent.id,
    name: agent.name ?? agent.agent_name,
    agentName: agent.agent_name ?? agent.name,
    status: agent.status ?? 'pending',
    findings: agent.findings ?? 0,
    durationMs: agent.duration_ms ?? agent.durationMs ?? null,
    summary: agent.summary ?? null,
    errorMessage: agent.error_message ?? agent.errorMessage ?? null,
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
      agentId: issue.agent_id ?? issue.agentId,
      agentName: issue.agent_name ?? issue.agentName,
      severity: issue.severity,
      title: issue.title,
      description: issue.description,
      suggestion: issue.suggestion ?? issue.suggested_fix,
      suggestedFix: issue.suggested_fix ?? issue.suggestion,
      line: issue.line ?? issue.start_line,
      startLine: issue.start_line ?? issue.line,
      endLine: issue.end_line,
      file: issue.file,
      category: issue.category,
      confidence: issue.confidence,
      explanation: issue.explanation,
      source: issue.source,
      diff: issue.diff,
      hasDiff: issue.has_diff ?? issue.hasDiff ?? false,
      validationStatus: issue.validation_status ?? issue.validationStatus,
      validationDetails: issue.validation_details ?? issue.validationDetails,
      originalFindingId: issue.original_finding_id ?? issue.originalFindingId,
      originalAgentId: issue.original_agent_id ?? issue.originalAgentId,
    })),
    agents,
    counts: {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
      total: 0,
      ...(payload.counts ?? {}),
    },
    durationMs: payload.duration_ms ?? null,
    fixDecisions: payload.fix_decisions ?? {},
    fixedCode: payload.fixed_code ?? null,
    isDemo: false,
  }
}

export function isPendingReview(review) {
  return (review?.status ?? 'pending') === 'pending'
}
