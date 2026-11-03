# Setup Guide - ALPHA CodeGuard AI

## Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.12+
- **Git**

## Quick Start

### 1. Clone the Repository
```bash
git clone <repository-url>
cd "Alpha CodeGuard AI"
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment file
cp .env.example .env

# Edit .env with your configuration (optional - works without API key)
# Start the server
uvicorn app.main:app --reload --port 8000
```

Backend will be available at:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment file
cp .env.example .env.local

# Start development server
npm run dev
```

Frontend will be available at http://localhost:5173

## Environment Variables

### Backend (.env)
| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | Application environment |
| `DATABASE_URL` | `sqlite:///./codeguard.db` | Database connection string |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed CORS origins |
| `MAX_CODE_LENGTH` | `200000` | Maximum code length in characters |
| `GEMINI_API_KEY` | `` | Google Gemini API key (optional) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model to use |
| `GEMINI_TIMEOUT_SECONDS` | `45` | Request timeout |
| `GEMINI_MAX_ATTEMPTS` | `3` | Max retry attempts |
| `SECRET_KEY` | dev placeholder | **Set a strong value in production** (`openssl rand -hex 32`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT lifetime |
| `RATE_LIMIT_ENABLED` | `true` | Rate limits on auth endpoints |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | `none` / empty | Legacy settings; only Gemini is implemented |

### Frontend (.env.local)
| Variable | Default | Description |
| --- | --- | --- |
| `VITE_APP_NAME` | `ALPHA CodeGuard AI` | Application name |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |

## Getting a Gemini API Key (Optional)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key
3. Add it to `backend/.env` as `GEMINI_API_KEY=your-key-here`
4. Restart the backend server

**Note:** Without a key the app still runs: reviews are stored with status `pending` and no findings. With a key that is invalid or out of quota, the review is stored as `error`/`completed_with_errors` with no quality score and the failure reason in `summary` — failures are never reported as clean results.

## Testing

### Backend Tests
```bash
cd backend
.venv\Scripts\activate  # or source .venv/bin/activate
python -m pytest -v
```

The suite disables auth rate limiting (`RATE_LIMIT_ENABLED=false`) and mocks all
Gemini calls, so it needs no API key and makes no network requests.

### Frontend Build
```bash
cd frontend
npm run build
```

### Frontend Lint
```bash
cd frontend
npm run lint
```

## Troubleshooting

### Database Issues
If you encounter database errors, delete `backend/codeguard.db` and restart the server.

### Port Already in Use
Change ports using `--port` flag:
```bash
uvicorn app.main:app --reload --port 8001
```
Update frontend `.env.local` accordingly.

### Module Not Found Errors
Ensure virtual environment is activated and dependencies are installed.

## Production Deployment

### Frontend (Vercel)
1. Connect repository to Vercel
2. Set build command: `npm run build`
3. Set output directory: `dist`
4. Add environment variable: `VITE_API_BASE_URL=<your-backend-url>`

### Backend (Render)
1. Create a new Web Service
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables from `.env.example`, including a real `SECRET_KEY`
5. Update `CORS_ORIGINS` to include your frontend URL
6. Keep `GEMINI_API_KEY` server-side only — never expose it as a `VITE_` variable

Schema changes are applied on startup by `ensure_schema()` (create tables plus
`ALTER TABLE ... ADD COLUMN user_id ON reviews`). No migration framework is used.
