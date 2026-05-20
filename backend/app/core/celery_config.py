import os
from celery import Celery

# Read your Valkey connection URL from environment variables, fallback to local default
VALKEY_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "atihmam_tasks",
    broker=VALKEY_URL,
    backend=VALKEY_URL,
)

# Configuration settings optimized for stable task running
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Automatically scan your app/tasks directory for shared tasks like process_cv
    imports=("app.tasks.cv_processing",),
)