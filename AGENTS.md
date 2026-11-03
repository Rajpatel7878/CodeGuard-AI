# AGENTS.md - ALPHA CodeGuard AI

## Project Overview
ALPHA CodeGuard AI is a professional multi-agent code review workspace developed by Team ALPHA. It uses a LangGraph-based orchestrator to coordinate five specialized AI agents for comprehensive code analysis.

## Architecture Overview

### Multi-Agent System
The system employs 5 specialized agents coordinated by a LangGraph orchestrator:

1. **Bug Detection Agent** - Identifies logical errors, null/None handling issues, indexing errors, resource leaks, unhandled exceptions
2. **Security Analysis Agent** - Detects SQL injection, XSS, hardcoded credentials, command injection, path traversal, weak cryptography
3. **Performance Optimization Agent** - Finds inefficient algorithms, unnecessary allocations, blocking operations, memory leaks
4. **Code Quality Agent** - Checks style, maintainability, complexity, naming conventions, best practices
5. **Fix & Validation Agent** - Generates fix suggestions with unified diffs and validates with static analysis tools

### Orchestration
- **Active orchestrator**: `app/agents/orchestrator.py` — static tools, four AI agents in a thread pool, then the Fix agent
- **Alternative**: `app/llm/graph.py` (LangGraph-shaped, sequential) is tested but not used by the API
- **Authentication**: JWT bearer tokens; review endpoints require a user and are owner-scoped
- **Deduplication**: Overlapping findings are merged intelligently
- **Quality Scoring**: Transparent heuristic scoring (100 - deductions by severity); failed reviews are unscored
- **Honest Degradation**: No API key → `pending` review; provider failure → `error`/`completed_with_errors` with the reason surfaced, never a fake clean result

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **Orchestration**: LangGraph
- **AI/LLM**: Google Gemini (google-genai)
- **Database**: SQLAlchemy 2.0 + SQLite
- **Validation**: Pydantic v2
- **Static Analysis**: Ruff, Bandit (Python), ESLint, cppcheck (multi-language support)

### Frontend
- **Framework**: React 19 + Vite
- **Styling**: Tailwind CSS v4
- **Editor**: Monaco Editor
- **Routing**: React Router DOM
- **Icons**: Lucide React

## Development Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use TypeScript/ESLint conventions for JavaScript/React
- Write clear, self-documenting code
- Add type hints where appropriate

### Safety Principles
- **Never execute submitted code** - All analysis is static
- **API keys never exposed** - Stored server-side only
- **Input validation** - All requests validated with Pydantic
- **Size limits enforced** - Configurable max code length
- **Error handling** - Graceful degradation on failures

### Testing
- Run backend tests: `cd backend && python -m pytest`
- Run frontend build: `cd frontend && npm run build`
- Run frontend lint: `cd frontend && npm run lint`

### Agent Development
When adding or modifying agents:
1. Follow the existing agent pattern (system instruction + analyze function)
2. Use the Gemini service through the module-level hook for testability
3. Normalize findings to the standard schema
4. Always catch exceptions for graceful degradation
5. Label findings as `ai_suggestion` source
6. Raise `GeminiServiceError` on failure instead of returning an empty success — the orchestrator records the agent as failed

## Environment Configuration
See `.env.example` files for required configuration.

## Deployment
- **Frontend**: Vercel
- **Backend**: Render
- **Database**: SQLite (development), consider PostgreSQL for production

## Team
**Team ALPHA** - ALPHA CodeGuard AI
