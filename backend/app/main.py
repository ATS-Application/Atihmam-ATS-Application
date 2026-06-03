# app/main.py
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.v1 import  auth, candidates, jobs, ingestion, feedback, health
from app.api.v1.analytics import router as analytics_router

settings = get_settings()


def run_webhook_setup():
    try:
        from app.services.webhook_manager import ensure_webhook_registered
        result = ensure_webhook_registered()
        print(f"[Drive webhook] {result['status']} — channel: {result.get('channel_id', 'N/A')}")
    except Exception as e:
        print(f"[Drive webhook] Warning: could not register webhook: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load the sentence transformer at startup
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _get_model)
    
    if settings.drive_folder_id:
        loop.run_in_executor(None, run_webhook_setup)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATS API",
        description="Intelligent Applicant Tracking System — Backend",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if getattr(settings, "app_env", "development") == "development" else None,
        redoc_url=None,
    )

    origins = getattr(settings, "allowed_origins", []) or []
    required_origins = [
        "https://atihmam-ats-application.vercel.app",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "https://same-acrylic-kirk-unity.trycloudflare.com",
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

    prefix = "/api/v1"
    app.include_router(auth.router,       prefix=prefix)
    app.include_router(candidates.router, prefix=prefix)
    app.include_router(jobs.router,       prefix=prefix)
    app.include_router(ingestion.router,  prefix=prefix)
    app.include_router(feedback.router,   prefix=prefix)
    app.include_router(health.router,     prefix=prefix)
    app.include_router(analytics_router, prefix="/api/v1")

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
