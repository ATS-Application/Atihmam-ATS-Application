# Setup Instructions - Backend

## ⚠️ SECURITY ALERT
This project has been fixed to prevent secret exposure:
- `.env` is now in `.gitignore`
- Use `.env.example` as a template for local development
- **NEVER commit `.env` files**

## Prerequisites
- Python 3.11+
- Redis/Valkey running on localhost:6379
- Google Drive API credentials (optional)

## Installation

### 1. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 2. Install dependencies
Using `uv` (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -r requirements.txt
```

### 3. Run the backend
```bash
uvicorn app.main:app --reload --port 8000
```

API docs will be available at: http://localhost:8000/docs

## Project Structure
```
backend/
├── app/
│   ├── main.py           # FastAPI app initialization
│   ├── config.py         # Settings/configuration
│   └── api/
│       └── v1/          # API v1 routes
├── core/
│   ├── security.py       # JWT & auth utilities
│   └── state_machine.py # Workflow state management
├── db/
│   ├── supabase_client.py
│   └── drive_channels.py
├── models/               # Data models
├── schemas/              # Pydantic schemas
├── services/             # Business logic
└── tasks/                # Celery tasks
```

## Environment Variables
See `.env.example` for all available configuration options.

### Key Settings
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`: Supabase API credentials
- `SECRET_KEY`: JWT signing key (min 64 chars)
- `GEMINI_API_KEY`: Google Generative AI key
- `DRIVE_FOLDER_ID`: Google Drive folder for document storage
- `WEBHOOK_BASE_URL`: URL for webhook callbacks (e.g., ngrok)

## Local Development
```bash
# Terminal 1: Start backend
uvicorn app.main:app --reload

# Terminal 2 (optional): Start Celery
celery -A app.tasks.celery_app worker --loglevel=info
```
