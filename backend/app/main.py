import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.v1 import auth, candidates, jobs, ingestion

settings = get_settings()

# 💡 Background task: Run webhook registration in a worker thread to avoid blocking
def run_webhook_setup():
    try:
        from app.services.webhook_manager import ensure_webhook_registered
        result = ensure_webhook_registered()
        print(f"[Drive webhook] {result['status']} — channel: {result.get('channel_id', 'N/A')}")
    except Exception as e:
        print(f"[Drive webhook] Warning: could not register webhook: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.drive_folder_id:
        asyncio.get_running_loop().run_in_executor(None, run_webhook_setup)
    yield

def create_app() -> FastAPI:
    app = FastAPI(
        title="ATS API",
        description="Applicant Tracking System — Backend",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env == "development" else None,
        redoc_url=None,
    )

    # Centralized CORS origin management
    origins = list(settings.allowed_origins) if settings.allowed_origins else []
    
    # Required development origins
    # Add this to your required_origins list in main.py
    required_origins = [
        "http://localhost:5173",
        "http://localhost:5174", # Added this
        "http://localhost:3000",
        "https://same-acrylic-kirk-unity.trycloudflare.com"
    ]
    
    for origin in required_origins:
        if origin not in origins:
            origins.append(origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(candidates.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(ingestion.router, prefix=prefix)

    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok", "env": settings.app_env}

    return app

# Initialize the application instance
app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)