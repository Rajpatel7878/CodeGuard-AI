# API Documentation - ALPHA CodeGuard AI

Base URL: `http://localhost:8000` (development)

## Endpoints

### Health Check

#### GET `/health`
Check API and database health status.

**Response (200 OK):**
```json
{
  "status": "ok",
  "service": "ALPHA CodeGuard AI API",
  "version": "0.3.0",
  "environment": "development",
  "database": "ok",
  "llm": {
    "provider": "gemini",
    "configured": true,
    "status": "configured" | "not_configured",
    "message": "Gemini analysis is enabled (gemini-3.8-flash)."
  }
}
```

**Response (503 Service Unavailable):** returned by the global handler for unexpected database errors.
```json
{
  "detail": "The review database is unavailable. Try again shortly."
}
```

---

### Authentication

All review endpoints require a bearer token (or the `access_token` cookie).

| Method | Path | Body / Query | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | `full_name, email, password, confirm_password, terms_accepted` | 201 with `{access_token, token_type, user}`; 400 if the email exists; rate limited 5/min |
| POST | `/api/auth/login` | `email, password, remember_me` | 200 with the same shape; 401 on bad credentials; rate limited 10/min |
| GET | `/api/auth/me` | — | Current user; 401 without a token |
| POST | `/api/auth/logout` | — | Clears the auth cookies |
| POST | `/api/auth/forgot-password` | `email` | Always 200, to avoid account enumeration; rate limited 3/min |
| POST | `/api/auth/reset-password` | `token, password, confirm_password` | 400 for invalid/expired tokens |
| GET | `/api/auth/google/login`, `/api/auth/google/callback` | — | Requires Google credentials |
| GET | `/api/auth/github/login`, `/api/auth/github/callback` | — | Requires GitHub credentials |

Passwords must be 8+ characters with at least one letter and one number. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30).

---

### Reviews

#### POST `/api/review`
Submit code for review. Triggers multi-agent analysis. **Requires authentication.**

**Request Body:**
```json
{
  "code": "string (required, max 200000 chars)",
  "language": "string (required)",
  "filename": "string (optional)"
}
```

**Supported Languages:** JavaScript, TypeScript, Python, Java, C#, C++, Go, Rust, PHP

**Agent `status` values:** `ok`, `error`, `timeout`, `skipped`, `pending` (no
key configured). A non-`ok` status always carries `error_message` where one
applies.

**Response (201 Created):**
```json
{
  "id": "rev_abc123",
  "status": "completed" | "completed_with_errors" | "pending" | "error",
  "language": "python",
  "language_label": "Python",
  "filename": "example.py",
  "lines": 10,
  "characters": 250,
  "quality_score": 85,
  "grade": "B",
  "summary": "Analysis complete.",
  "duration_ms": 1250,
  "created_at": "2026-11-02T06:42:52.325783Z",
  "code": "...",
  "issues": [
    {
      "id": "bug-001",
      "agent_id": "bug",
      "agent_name": "Bug Detection",
      "severity": "High",
      "title": "Potential null reference",
      "description": "...",
      "suggestion": "...",
      "line": 15
    }
  ],
  "agents": [
    {
      "id": "bug",
      "name": "Bug Detection Agent",
      "status": "ok",
      "findings": 2,
      "duration_ms": 300
    }
  ],
  "counts": {
    "critical": 0,
    "high": 1,
    "medium": 1,
    "low": 0,
    "info": 0,
    "total": 2
  },
  "fix_decisions": {},
  "fixed_code": null
}
```

**Status values:**
- `pending` — no `GEMINI_API_KEY` configured; no agent ran and `quality_score` is `null`.
- `completed` — every agent ran; score and grade are set.
- `completed_with_errors` — some agents failed; `quality_score` is `null`.
- `error` — every attempted agent failed; `quality_score` is `null` and `summary` names the failures.

**Errors:**
- `401 Unauthorized` - Missing/invalid token
- `413 Payload Too Large` - Code exceeds max length
- `422 Unprocessable Entity` - Empty code or unsupported language

---

#### GET `/api/reviews`
List the caller's reviews with pagination. **Requires authentication.**

**Query Parameters:**
- `limit` (int, default: 50, min: 1, max: 100)
- `offset` (int, default: 0, min: 0)
- `language` (string, optional) - Filter by language

**Response (200 OK):**
```json
{
  "items": [...], // Array of ReviewResponse objects
  "total": 10,
  "limit": 50,
  "offset": 0
}
```

**Errors:**
- `422 Unprocessable Entity` - Invalid pagination parameters

---

#### GET `/api/reviews/{review_id}`
Get a specific review by ID. **Requires authentication; only the owner can read it.**

**Response (200 OK):**
Same as POST /api/review response

**Errors:**
- `401 Unauthorized` - Missing/invalid token
- `404 Not Found` - Unknown review, or one belonging to another account

---

#### POST `/api/reviews/{review_id}/fix-decision`
Set user decision on a fix suggestion. **Requires authentication and ownership.**

**Query Parameters:**
- `decision` (string, required) - One of: `accepted`, `rejected`, `muted`
- `finding_id` (string, required) - ID of a finding in that review

**Response (200 OK):**
Updated ReviewResponse object. `fix_decisions` maps finding id → decision. When a
fix is accepted and the Fix agent produced updated code, `fixed_code` holds that
code; otherwise it stays `null` (nothing is invented).

**Errors:**
- `401 Unauthorized` - Missing/invalid token
- `404 Not Found` - Review not found, not owned by the caller, or finding not in the review
- `422 Unprocessable Entity` - `decision` is not `accepted`/`rejected`/`muted`

---

## Error Responses

All error responses follow this format:
```json
{
  "detail": "Error message description"
}
```

## Rate Limiting

Auth endpoints are rate limited per client IP with slowapi: register 5/min,
login 10/min, forgot-password 3/min, reset-password 5/min. Exceeding a limit
returns `429` with `{"error": "Rate limit exceeded: ..."}`. Set
`RATE_LIMIT_ENABLED=false` to disable (the test suite does this).

Review endpoints are not rate limited.

## Authentication

JWT bearer tokens (`HS256`, signed with `SECRET_KEY`) are issued by
`/api/auth/login` and `/api/auth/register`. Send `Authorization: Bearer <token>`
or rely on the `access_token` cookie set by the OAuth callbacks. Invalid or
expired tokens produce `401`. Reviews are scoped per account.
