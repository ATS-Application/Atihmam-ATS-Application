import uuid
import io
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_drive_service():
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.google_drive_credentials_json,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_pdf_files(folder_id: str) -> list[dict]:
    service = _get_drive_service()
    query = (
        f"'{folder_id}' in parents"
        " and mimeType='application/pdf'"
        " and trashed=false"
    )
    result = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, mimeType, createdTime, modifiedTime)",
            orderBy="createdTime desc",
        )
        .execute()
    )
    return result.get("files", [])


def download_file_bytes(file_id: str) -> bytes:
    service = _get_drive_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def get_file_metadata(file_id: str) -> dict:
    service = _get_drive_service()
    return (
        service.files()
        .get(fileId=file_id, fields="id, name, mimeType, createdTime, modifiedTime")
        .execute()
    )


def register_webhook(folder_id: str, webhook_url: str) -> dict:
    service = _get_drive_service()
    channel_id = str(uuid.uuid4())
    expiration_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000
    )
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url,
        "expiration": expiration_ms,
    }
    response = service.files().watch(fileId=folder_id, body=body).execute()
    return {
        "channel_id": response["id"],
        "resource_id": response["resourceId"],
        "expiration_ms": int(response.get("expiration", expiration_ms)),
        "expiration_iso": datetime.fromtimestamp(
            int(response.get("expiration", expiration_ms)) / 1000,
            tz=timezone.utc,
        ).isoformat(),
    }


def stop_webhook(channel_id: str, resource_id: str) -> None:
    service = _get_drive_service()
    service.channels().stop(
        body={"id": channel_id, "resourceId": resource_id}
    ).execute()