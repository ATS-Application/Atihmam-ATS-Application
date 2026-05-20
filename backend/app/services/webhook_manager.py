import time
from app.config import get_settings
from app.services.drive_service import register_webhook, stop_webhook
from app.db.drive_channels import save_channel, get_active_channel, delete_channel

RENEWAL_BUFFER_MS = 24 * 60 * 60 * 1000  # 1 day


def ensure_webhook_registered() -> dict:
    settings = get_settings()
    folder_id = settings.drive_folder_id
    webhook_url = f"{settings.webhook_base_url}/api/v1/ingestion/drive/webhook"

    if not folder_id:
        raise ValueError("DRIVE_FOLDER_ID is not set in .env")

    existing = get_active_channel(folder_id)

    if existing:
        now_ms = int(time.time() * 1000)
        time_remaining_ms = existing["expiration_ms"] - now_ms

        if time_remaining_ms > RENEWAL_BUFFER_MS:
            return {
                "status": "active",
                "channel_id": existing["channel_id"],
                "expires_in_hours": round(time_remaining_ms / 3_600_000, 1),
            }

        try:
            stop_webhook(existing["channel_id"], existing["resource_id"])
        except Exception:
            pass
        delete_channel(existing["channel_id"])

    channel = register_webhook(folder_id, webhook_url)
    save_channel(
        channel_id=channel["channel_id"],
        resource_id=channel["resource_id"],
        folder_id=folder_id,
        expiration_ms=channel["expiration_ms"],
    )
    return {
        "status": "registered",
        "channel_id": channel["channel_id"],
        "expires_at": channel["expiration_iso"],
    }