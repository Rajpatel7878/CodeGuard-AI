# Architecture Documentation - ALPHA CodeGuard AI

## System Overview

ALPHA CodeGuard AI is a full-stack application with a React frontend and FastAPI backend. Code review is coordinated by the thread-based multi-agent orchestrator in `app/agents/orchestrator.py`; `app/llm/graph.py` is an alternative LangGraph-shaped implementation that the API does not use.

## High-Level Architecture

```
┌─────────────┐  HTTP/JSON + JWT  ┌─────────────┐
│   React SPA │ ◄────────────────► │   FastAPI    │
│  (Frontend)  │                    │   (Backend)   │
└─────────────┘                    └─────────────┘
                                          │
                                    ┌─────▼──────┐
                                    │Orchestrator │
                                    │(thread pool)│
                                    └─────┬─────┘
                                          │
                                    ┌─────▼─────────────────────────┐
                                    │      5 Specialized Agents      │
                                    ├─────────────────────────────────┤
                                    │  • Bug Detection               │
                                    │  • Security Analysis           │
                                    │  • Performance Optimization    │
                                    │  • Code Quality                │
                                    │  • Fix & Validation            │
                                    └─────────────┬───────────────────┘
                                                  │
                                            ┌─────▼─────┐
                                            │   Gemini   │
                                            │     API    │
                                            └───────────┘
                                                  │
                                            ┌─────▼─────┐
                                            │   SQLite   │
                                            │  Database  │
                                            └───────────┘
```

## Backend Architecture

### Core Components

#### API Layer (`app/api/`)
- `health.py` - Health check endpoint
- `auth.py` - Register, login, logout, current user, password reset, OAuth
- `deps.py` - `get_current_user` dependency (bearer token or cookie)
- `limits.py` - Shared slowapi rate limiter
- `reviews.py` - Review submission, retrieval, and fix decision endpoints (auth required, owner-scoped)

#### Orchestration (`app/agents/orchestrator.py`)
- Runs static tools, then four AI agents in parallel threads, then the fix agent
- Per-agent timeout, failure isolation, deduplication, honest overall status

#### LLM layer (`app/llm/`)
- `gemini_service.py` - Gemini API integration with retry logic and response validation
- `client.py` - Reports whether analysis is configured (drives `/health`)
- `schemas.py` - Validated LLM response schemas
- `prompts.py` - Shared prompt scaffolding
- `graph.py` / `state.py` - Alternative LangGraph-shaped orchestrator, **not used by the API**

#### Agents (`app/agents/`)
- `bug_agent.py` - Bug detection logic
- `security_agent.py` - Security vulnerability detection
- `performance_agent.py` - Performance analysis
- `quality_agent.py` - Code quality assessment
- `fix_agent.py` - Fix generation with diff creation
- `static_tools.py` - Static analysis tool integration
- `deduplication.py` - Finding deduplication logic
- `registry.py` - Agent registry

#### Services (`app/services/`)
- `review_service.py` - Review persistence, per-user scoping, response assembly
- `auth_service.py` - Argon2 password hashing and JWT creation/verification

#### Database (`app/database/`)
- `models.py` - `Review` (owned by a `User`), `User`, `PasswordResetToken`
- `session.py` - Engine, session factory, request-scoped dependency

#### Schemas (`app/schemas/`)
- `review.py` - Request/response models
- `auth.py` - Auth request/response models
- `languages.py` - Language validation

### Workflow

1. **Authentication** - Bearer token (or cookie) resolved to a `User`
2. **Input Validation** - Code non-empty, supported language, size limit
3. **Configuration gate** - Without `GEMINI_API_KEY` the review is stored as `pending` and no agent runs
4. **Static Analysis** - Ruff/Bandit (Python), ESLint (JS/TS), cppcheck (C/C++) if installed
5. **Parallel Agent Execution** - Bug, Security, Performance, Quality in a thread pool with a per-agent timeout
6. **Aggregation** - Deduplicate AI and static findings
7. **Fix Generation** - Fix & Validation agent receives the deduplicated findings
8. **Scoring** - Severity-deduction score, only when the review completed fully
9. **Persistence** - Findings, agents, score, and owner stored in SQLite
10. **Response** - Structured review returned to the client

Failure semantics: an agent exception is caught per agent and recorded as
`error`/`timeout`; other agents continue. The overall status becomes
`completed_with_errors` when some agents failed and `error` when every agent
that had work to do failed. Failed reviews receive no quality score.

## Frontend Architecture

### Components (`src/components/`)
- `Navbar.jsx` - Navigation
- `Sidebar.jsx` - Sidebar navigation
- `CodeEditor.jsx` - Monaco editor integration
- `AgentCard.jsx` - Agent status display
- `IssueCard.jsx` - Issue/finding display
- `ScoreCard.jsx` - Quality score visualization
- `StatusBadge.jsx` - Status indicators

### Pages (`src/pages/`)
- `Dashboard.jsx` - Main dashboard
- `ReviewCode.jsx` - Code submission page
- `Results.jsx` - Review results display
- `ReviewHistory.jsx` - Historical reviews
- `Settings.jsx` - Settings page

### State Management
- `context/AuthContext.jsx` - Session, login/register/logout, token storage
- `context/ReviewContext.jsx` - Per-account review list, settings, API calls
  (reloads when the signed-in account changes and clears on sign-out)

### Utilities (`src/lib/`)
- `api.js` - API client
- `reviewMapper.js` - Data transformation
- `format.js` - Formatting helpers
- `severity.js` - Severity utilities

## Data Flow

1. User submits code via frontend
2. Frontend validates and sends POST to `/api/review`
3. Backend creates review record, runs LangGraph orchestrator
4. Orchestrator coordinates all agents
5. Agents call Gemini API (if configured) or return gracefully
6. Results aggregated, deduplicated, scored
7. Stored in SQLite database
8. Response returned to frontend
9. Frontend displays results with agents, issues, scores

## Security Considerations

- **No Code Execution**: Submitted code is never executed, imported, or compiled
- **API Key Protection**: Gemini keys stored server-side only, never exposed
- **Input Sanitization**: All inputs validated with Pydantic
- **Size Limits**: Configurable max code length (default 200KB)
- **CORS**: Restricted to configured origins
- **Error Scrubbing**: API errors don't leak sensitive information; the Gemini key is redacted from error text
- **Filename Sanitization**: Paths reduced to basename
- **Authentication**: Argon2 password hashing, HS256 JWTs, rate-limited auth endpoints
- **Authorization**: reviews are owner-scoped; foreign IDs return 404, not 403
- **No fabricated success**: provider failures surface as `error`/`completed_with_errors` with no score

## Scalability Considerations

- **Current**: SQLite, synchronous operations - suitable for hackathon/demo
- **Future**: PostgreSQL, async processing, caching, rate limiting
- **Horizontal Scaling**: Would need distributed task queue for agent execution
