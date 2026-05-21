# app/core/celery_config.py
import os
from celery import Celery

# Change the default fallback string here to use RabbitMQ
BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
BACKEND_URL = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

celery_app = Celery(
    "atihmam_tasks",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=[
        "app.tasks.cv_processing",
        "app.tasks.drive_sync",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)