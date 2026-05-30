# backend/app/core/celery_config.py
from celery import Celery
from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "atihmam_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.cv_processing",
        "app.tasks.drive_sync",
    ],
)

celery_app.conf.update(
    # ── Serialization ────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # ── Reliability ──────────────────────
    task_acks_late=True,                  # ack after task completes
    worker_prefetch_multiplier=1,         # one task at a time (solo pool)
    task_reject_on_worker_lost=True,      # requeue if worker dies

    # ── Timeouts ─────────────────────────
    task_time_limit=7200,                 # hard kill after 2h
    task_soft_time_limit=6000,            # soft warning at 100min
    broker_heartbeat=120,                 # heartbeat every 2min
    broker_transport_options={
        "confirm_publish": True,
    },

    # ── Results ──────────────────────────
    result_expires=3600,                  # results kept 1h
)