# ALPHA CodeGuard AI
Live Website: https://code-guard-ai-rho.vercel.app/

Professional multi-agent code review workspace by **Team ALPHA**.

- **Phase 1** — React + Vite + Tailwind frontend.
- **Phase 2** — FastAPI + SQLAlchemy + SQLite backend, wired to the frontend.
- **Phase 3** — Gemini integration with validated structured findings.
- **Phase 4** — Accounts, per-user review ownership, honest failure reporting.

> **AI status — wired.** `POST /api/review` runs the five agents through `app/agents/orchestrator.py`. Without `GEMINI_API_KEY` the review is stored with status `pending` and no findings. If Gemini fails (bad key, quota, outage) the agents are marked `error`, the review status is `error` or `completed_with_errors`, and **no quality score is assigned** — a failed review is never scored 100/100. The backend never executes submitted code.

## Architecture

```
React SPA (localhost:5173)
        │  JSON over HTTP (VITE_API_BASE_URL)
        ▼
FastAPI (localhost:8000)
  app/api/        routes: /health, /api/auth/*, /api/review, /api/reviews
  app/schemas/    Pydantic request/response models + language validation
  app/services/   review lifecycle, persistence, response assembly, auth
  app/analyzers/  analysis pipeline (Gemini gate + finding→Issue mapping)
  app/llm/        Gemini review service, prompts, schemas, graph (unused)
  app/agents/     orchestrator + five agents, static tools, deduplication
  app/database/   SQLAlchemy engine, sessions, Review/User models
        │
        ▼
SQLite database (backend/codeguard.db by default)
```

## Stack

**Frontend:** React 19, Vite, Tailwind CSS v4, React Router, Monaco Editor (bundled locally), Lucide icons.
**Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, Uvicorn.

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- API: <http://localhost:8000>
- Swagger docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Run `uvicorn` from `backend/` so the default `sqlite:///./codeguard.db` lands beside the app.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:5173>. The first load fetches history from the API; if the backend is not running the UI shows an explicit “API unavailable” state with retry.

## API

| Method | Path                                | Success | Errors                                                       |
| ------ | ----------------------------------- | ------- | ------------------------------------------------------------ |
| GET    | `/health`                           | 200     | 503 for unexpected database failures                         |
| POST   | `/api/auth/register`                | 201     | 400 email taken · 422 invalid body · 429 rate limited        |
| POST   | `/api/auth/login`                   | 200     | 401 bad credentials · 429 rate limited                       |
| GET    | `/api/auth/me`                      | 200     | 401 not authenticated                                        |
| POST   | `/api/auth/logout`                  | 200     | —                                                            |
| POST   | `/api/auth/forgot-password`         | 200     | 429 rate limited                                             |
| POST   | `/api/auth/reset-password`          | 200     | 400 invalid/expired token                                    |
| POST   | `/api/review`                       | 201     | 401 · 413 code too large · 422 empty code / bad language     |
| GET    | `/api/reviews`                      | 200     | 401 · 422 invalid `limit`/`offset`                           |
| GET    | `/api/reviews/{id}`                 | 200     | 401 · 404 unknown or not yours                               |
| POST   | `/api/reviews/{id}/fix-decision`    | 200     | 401 · 404 review/finding · 422 invalid decision              |

Every review endpoint requires `Authorization: Bearer <token>` (or the `access_token` cookie). Reviews are scoped to the account that created them: another account gets `404`, never someone else's code.

`GET /api/reviews` accepts `limit` (1–100, default 50), `offset` (≥ 0), and optional `language`, and returns `{ items, total, limit, offset }` for the signed-in account only.

### Review request

```json
{
  "code": "print('hello')",
  "language": "python",
  "filename": "main.py"
}
```

Supported languages: JavaScript, TypeScript, Python, Java, C#, C++, Go, Rust, PHP.

### Review response (pending — no `GEMINI_API_KEY`)

```json
{
  "id": "rev_1a2b3c4d5e6f",
  "status": "pending",
  "language": "python",
  "language_label": "Python",
  "filename": "main.py",
  "lines": 1,
  "characters": 15,
  "quality_score": null,
  "grade": null,
  "created_at": "2026-10-30T23:30:00+00:00",
  "code": "print('hello')",
  "issues": [],
  "agents": [
    {
      "id": "bug",
      "name": "Bug Detection Agent",
      "status": "pending",
      "findings": 0,
      "duration_ms": null
    }
  ],
  "counts": { "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0 },
  "summary": "AI analysis is not configured. Set GEMINI_API_KEY in the backend environment ...",
  "duration_ms": null
}
```

## Analysis pipeline

`app/llm/gemini_service.py` is the only code that talks to Google. It uses the official `google-genai` Python SDK and a currently supported model (`gemini-3.8-flash` by default). Submitted source text is sent to the model as prompt text and is never executed, compiled, or imported.

```
POST /api/review
      │
      ▼
app/analyzers/pipeline.py   gate on GEMINI_API_KEY, then map findings → Issue
      │
      ▼
app/agents/orchestrator.py  static tools + 4 agents in parallel + fix agent
      │
      ▼
app/llm/prompts.py      system rules + review prompt (code comes last, as data)
      │
      ▼
GeminiCodeReviewService  timeout · retry with backoff · rate-limit handling
      │  JSON text
      ▼
app/llm/schemas.py      Pydantic validation → GeminiAnalysis
      │
      ▼
validated findings (suggestions only — never claimed as verified fixes)
```

Behaviour that matters:

- **No key → `pending`.** No agent is called, no findings, no score.
- **Provider failure → `error` / `completed_with_errors`.** Gemini rejections, quota/429, 5xx, timeouts, and malformed model output are raised by each agent and recorded per-agent; the review summary names the failures and **no quality score is assigned** unless the review completed fully.
- **Static tools run regardless.** Ruff/Bandit (Python), ESLint (JS/TS), cppcheck (C/C++) contribute findings only when the binary is installed and reports real output. Otherwise the run is honestly empty.
- **Quality score is a documented heuristic**: 100 minus 20/10/5/2/0 per Critical/High/Medium/Low/Info finding.

### The LangGraph module

`app/llm/graph.py` contains a second, sequential orchestrator with a LangGraph-shaped state object. **The API does not use it** — `POST /api/review` goes through `app/agents/orchestrator.py`. It is retained (and tested) as an alternative implementation; wiring two different orchestrators per deployment would produce different results for the same code.

### Configure Gemini

1. Create a key at <https://aistudio.google.com/apikey>.
2. In `backend/.env`, set:

   ```bash
   GEMINI_API_KEY=your-key-goes-here
   GEMINI_MODEL=gemini-3.8-flash
   ```

3. Restart the backend. `GEMINI_API_KEY` is read only by the server: it is never sent to the frontend, never written to logs, and never included in an API response (error messages are scrubbed of it before they are raised).
4. Verify the client builds without contacting Google:

   ```bash
   cd backend
   .venv\Scripts\python -c "from app.llm.gemini_service import GeminiCodeReviewService as S; print(S.from_settings())"   # Windows
   # .venv/bin/python -c "..."                                                                                          # macOS / Linux
   ```

   The printed object shows `configured=True/False` and never the key.

```python
from app.llm.gemini_service import get_gemini_service

analysis = get_gemini_service().analyze(
    code="query = 'SELECT * FROM users WHERE name = ' + name\n",
    language="python",
    filename="users.py",
)
with open("report.json", "w") as handle:
    handle.write(analysis.model_dump_json(indent=2))
```

### Structured response

```json
{
  "summary": "One exploitable input-handling issue; the rest of the file is consistent.",
  "model_name": "gemini-3.8-flash",
  "warnings": [],
  "findings": [
    {
      "id": "sql-string-concat",
      "title": "SQL query built by string concatenation",
      "description": "The name argument is concatenated straight into the query text instead of being bound as a parameter.",
      "severity": "High",
      "category": "security",
      "file": "users.py",
      "start_line": 3,
      "end_line": 4,
      "suggested_fix": "Use a parameterized query: conn.execute('SELECT * FROM users WHERE name = ?', (name,)).",
      "confidence": 0.9,
      "explanation": "Untrusted input can rewrite the statement, so a crafted name can return other rows or drop data.",
      "source": "ai_suggestion"
    }
  ]
}
```

Rules enforced on the way through:

- `severity` must be one of `Critical`, `High`, `Medium`, `Low`, `Info` (case-insensitive on input).
- `confidence` is `0.0`–`1.0`; a percentage such as `85` is normalized to `0.85`.
- `start_line`/`end_line` must be ordered and inside the submission. Out-of-range findings are dropped and recorded in `warnings`.
- Every model finding is an `ai_suggestion`. A model that labels its own output `static_analysis` is downgraded, because no static analyzer confirmed it.
- `file` is reduced to a bare file name; duplicate finding ids are made unique.
- Malformed JSON, non-object JSON, missing fields, unknown severities, and inverted line ranges raise `GeminiResponseError` instead of returning partial data.

Failures are raised as `GeminiServiceError` subclasses with operator-readable messages: `GeminiNotConfiguredError` (no key or SDK missing), `GeminiTimeoutError`, `GeminiRateLimitError` (HTTP 429), `GeminiRequestRejectedError` (400/401/403/404 — not retried), and `GeminiResponseError` (blocked, truncated, empty, or invalid output). Transient failures (429, 408, 5xx, timeouts, network errors) are retried up to `GEMINI_MAX_ATTEMPTS` with exponential backoff and jitter.

## Environment variables

### Backend (`backend/.env.example`)

| Variable            | Default                                       | Purpose                              |
| ------------------- | --------------------------------------------- | ------------------------------------ |
| `APP_ENV`           | `development`                                 | Reported by `/health`.               |
| `DATABASE_URL`      | absolute `sqlite:///…/codeguard.db`           | SQLAlchemy database URL.             |
| `CORS_ORIGINS`      | `http://localhost:5173,http://127.0.0.1:5173` | Allowed browser origins.             |
| `MAX_CODE_LENGTH`   | `200000`                                      | Maximum submitted characters (413).  |
| `GEMINI_API_KEY`    | _(empty)_                                     | Gemini key. Server-side only.        |
| `GEMINI_MODEL`      | `gemini-3.8-flash`                            | Gemini model id.                     |
| `GEMINI_TIMEOUT_SECONDS` | `45`                                     | Per-attempt request timeout.         |
| `GEMINI_MAX_ATTEMPTS` | `3`                                         | Total attempts per review.           |
| `SECRET_KEY`        | dev placeholder                               | JWT signing key. **Change in production.** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                                | Access-token lifetime.               |
| `RATE_LIMIT_ENABLED`| `true`                                        | Auth-endpoint rate limits.           |
| `GOOGLE_CLIENT_ID` / `_SECRET` | _(empty)_                           | Optional Google OAuth.               |
| `GITHUB_CLIENT_ID` / `_SECRET` | _(empty)_                           | Optional GitHub OAuth.               |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | `none` / _(empty)_ / _(empty)_ | Legacy Phase-2 settings; only Gemini is implemented. |

### Frontend (`frontend/.env.example`)

| Variable           | Default                 | Purpose                          |
| ------------------ | ----------------------- | -------------------------------- |
| `VITE_APP_NAME`    | `ALPHA CodeGuard AI`    | Name shown in the navbar.        |
| `VITE_API_BASE_URL`| `http://localhost:8000` | FastAPI base URL (no slash).     |

Vite and python-dotenv read `.env.local` / `.env` respectively. Restart the servers after changes.

## Project structure

```
backend/
├── app/
│   ├── api/            health, auth, reviews, deps, limits
│   ├── agents/         orchestrator, five agents, static_tools, deduplication
│   ├── analyzers/      base.py, pipeline.py (Gemini gate + Issue mapping)
│   ├── database/       session.py, models.py (Review, User, PasswordResetToken)
│   ├── llm/            client.py, gemini_service.py, prompts.py, schemas.py,
│   │                   graph.py/state.py (alternative orchestrator, unused)
│   ├── schemas/        review.py, auth.py, languages.py
│   ├── services/       review_service.py, auth_service.py
│   ├── config.py
│   └── main.py
├── tests/              API, auth, agents, orchestrator, pipeline, Gemini service
│                       (mocked — no API key needed)
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── .env.example

frontend/
├── src/
│   ├── components/     Navbar, Sidebar, CodeEditor, UploadCode, AgentCard,
│   │                   IssueCard, ScoreCard, StatusBadge, LoadingIndicator, …
│   ├── context/        AuthContext, ReviewContext (per-account history)
│   ├── lib/            api.js (central API client), reviewMapper.js, formatting
│   └── pages/          Dashboard, ReviewCode, Results, ReviewHistory, Settings,
│                       Login, Register, ForgotPassword, ResetPassword, AuthCallback
└── .env.example
```

## Safety and data handling

- Submitted code is stored as text for display; it is **never executed or imported**.
- Filenames are reduced to a basename before storage.
- Request bodies are validated by Pydantic and capped by `MAX_CODE_LENGTH`.
- The API is read-only with respect to analysis results: it never invents findings, scores, or durations.
- CORS is limited to the configured local frontend origins.
- Passwords are hashed with Argon2; JWTs are signed with `SECRET_KEY`.
- Review endpoints require authentication and only return the caller's own reviews.
- Auth endpoints are rate limited per IP (`RATE_LIMIT_ENABLED`).

## Testing

```bash
cd backend
.venv\Scripts\python -m pytest      # Windows
# .venv/bin/python -m pytest        # macOS / Linux
```

`tests/test_gemini_service.py` mocks the Gemini client, so the suite needs no API key and never contacts Google. It covers valid and fenced JSON, empty findings, malformed and non-object JSON, missing fields, unknown severities, inverted and out-of-range line numbers, static-analysis relabeling, duplicate ids, percentage confidence, prompt-injection placement, 429/503/timeouts with backoff, non-retried 400/403/404 errors, blocked and truncated responses, missing configuration, and key redaction.

Frontend checks:

```bash
cd frontend
npm run build
npm run lint
```

## Verification performed

- `python -m pytest` — **195 passed**, no failures. Covers the API contract, auth and ownership, agent prompts/parsing, orchestrator failure isolation and deduplication, the analyzer pipeline wiring, and the Gemini service with a fake client (no key, no network).
- `python -m compileall app` — clean.
- `npm run build` — passes (Vite warns about the ~4.4 MB Monaco bundle).
- `npm run lint` — passes with non-blocking warnings only.
- **Live API** — `/health` reports `database: ok` and `llm.status: configured` with a real key; unauthenticated `POST /api/review` returns 401; register → submit → list → get works; reviews are scoped per account; the schema migration added `reviews.user_id` to an existing database file.
- **Live Gemini call** — attempted with the configured key. The model id is valid, but the key's quota was exhausted, so the provider returned HTTP 429/503. The review correctly came back as `status: error`, `quality_score: null`, all four agents `error`, the fix agent `skipped`, and the summary naming the rate-limit failure. **A successful live AI review could not be observed in this environment.**
- **Not run:** browser automation (no harness installed) and static-tool execution (ruff/bandit/eslint/cppcheck are not installed here; that path is covered by mocked tests only).

## Known limitations

- Gemini findings are suggestions from a language model. `suggested_fix` and diffs are never compiled, executed, or verified.
- Quality scoring is a fixed severity-deduction heuristic, not a measured assessment. Reviews that fail or partially fail are intentionally left unscored.
- `app/llm/graph.py` is a second orchestration implementation that is not used by the API; see the note above.
- Password reset generates a token, but no email provider is configured, so the token is never delivered (and deliberately not logged).
- Google/GitHub OAuth requires client credentials; the Google callback verifies the ID token through Google's `tokeninfo` endpoint and checks the audience.
- No delete or export endpoints for stored reviews.
- SQLite and a synchronous SQLAlchemy session are single-node. There is no task queue, so a review holds the request for the duration of the agents.
- Review responses include the full stored code; review lists are capped at 100 items per page.
- Schema changes are applied by a small `ensure_schema()` helper (create + `ALTER TABLE ADD COLUMN`), not a migration framework.
- No automated OpenAPI schema drift test; request/response shapes are covered by API tests.

## Next steps

- Add a task queue so reviews run asynchronously and the UI can poll progress.
- Add an email provider for password reset delivery.
- Install ruff/bandit/eslint/cppcheck in the deployment image to enable verified static findings.
