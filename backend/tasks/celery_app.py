from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ats",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.cv_processing", "app.tasks.drive_sync"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "renew-drive-webhook-every-12h": {
            "task": "app.tasks.drive_sync.renew_drive_webhook",
            "schedule": 12 * 60 * 60,
        },
        "sync-drive-folder-daily": {
            "task": "app.tasks.drive_sync.sync_drive_folder",
            "schedule": 24 * 60 * 60,
        },
    },
)