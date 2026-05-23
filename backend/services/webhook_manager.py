"""Webhook management for Google Drive integration."""

from app.db.drive_channels import create_drive_channel
from app.config import get_settings


def ensure_webhook_registered():
    """Ensure webhook is registered for Google Drive changes."""
    try:
        settings = get_settings()
        if not settings.drive_folder_id or not settings.webhook_base_url:
            return {
                "status": "skipped",
                "reason": "drive_folder_id or webhook_base_url not configured",
            }

        # Register or update the drive channel
        channel_id = create_drive_channel(
            folder_id=settings.drive_folder_id,
            webhook_url=f"{settings.webhook_base_url}/api/v1/ingestion/webhook/drive",
        )

        return {"status": "registered", "channel_id": channel_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}
