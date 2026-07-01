from __future__ import annotations

import io
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from http.client import IncompleteRead
from ssl import SSLError

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "image/png",
    "image/jpeg",
    "image/webp",
}


def _persist_token(creds: Credentials) -> None:
    with open(TOKEN_PATH, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())


def _get_credentials() -> Credentials:
    settings = get_settings()
    creds: Credentials | None = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist_token(creds)
        return creds

    if not settings.google_drive_credentials_json:
        raise FileNotFoundError("GOOGLE_DRIVE_CREDENTIALS_JSON is not set")
    if not os.path.exists(settings.google_drive_credentials_json):
        raise FileNotFoundError(
            f"OAuth credentials file not found: {settings.google_drive_credentials_json!r}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        settings.google_drive_credentials_json,
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _persist_token(creds)
    return creds


def _build_service():
    return build("drive", "v3", credentials=_get_credentials(), cache_discovery=False)


@lru_cache(maxsize=1)
def _get_drive_service():
    return _build_service()


def _service_with_retry():
    try:
        return _get_drive_service()
    except (TransportError, HttpError):
        _get_drive_service.cache_clear()
        return _get_drive_service()


def _mime_query() -> str:
    return "(" + " or ".join(
        f"mimeType='{mime_type}'" for mime_type in sorted(SUPPORTED_MIME_TYPES)
    ) + ")"


def _list_files_in_folder(service, folder_id: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
    query = f"'{folder_id}' in parents and {_mime_query()} and trashed=false"
    request = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, mimeType, createdTime, modifiedTime, parents), nextPageToken",
            orderBy="createdTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token,
        )
    )
    response = request.execute()
    return response.get("files", []), response.get("nextPageToken")


def _list_subfolders(service, folder_id: str) -> list[str]:
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    return [item["id"] for item in response.get("files", [])]


def list_pdf_files(folder_id: str) -> list[dict]:
    """List supported CV files in a Drive folder and all nested subfolders, newest first."""
    service = _service_with_retry()
    files: list[dict] = []
    queue = [folder_id]
    visited: set[str] = set()

    while queue:
        current_folder_id = queue.pop()
        if current_folder_id in visited:
            continue
        visited.add(current_folder_id)

        page_token: str | None = None
        while True:
            folder_files, next_page_token = _list_files_in_folder(service, current_folder_id, page_token)
            files.extend(folder_files)
            if not next_page_token:
                break
            page_token = next_page_token

        for child_folder_id in _list_subfolders(service, current_folder_id):
            queue.append(child_folder_id)

    return sorted(files, key=lambda item: item.get("createdTime", ""), reverse=True)


def download_file_bytes(file_id: str, max_retries: int = 5) -> bytes:
    retryable = (SSLError, IncompleteRead, TimeoutError, ConnectionError, OSError)

    for attempt in range(max_retries):
        try:
            service = _service_with_retry()
            request = service.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request, chunksize=4 * 1024 * 1024)

            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue()

        except HttpError as exc:
            if exc.status_code < 500 or attempt == max_retries - 1:
                raise
            wait = 2 ** attempt

        except retryable:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt

        _get_drive_service.cache_clear()
        time.sleep(wait)

    raise RuntimeError(f"Download failed after {max_retries} attempts: {file_id}")


def get_file_metadata(file_id: str) -> dict:
    service = _service_with_retry()
    return (
        service.files()
        .get(
            fileId=file_id,
            fields="id, name, mimeType, createdTime, modifiedTime",
            supportsAllDrives=True,
        )
        .execute()
    )


def get_start_page_token() -> str:
    service = _service_with_retry()
    return service.changes().getStartPageToken().execute()["startPageToken"]


def register_webhook(folder_id: str, webhook_url: str) -> dict:
    settings = get_settings()
    service = _service_with_retry()
    start_page_token = get_start_page_token()

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
    if settings.drive_webhook_token:
        body["token"] = settings.drive_webhook_token

    response = service.changes().watch(pageToken=start_page_token, body=body).execute()
    actual_expiration_ms = int(response.get("expiration", expiration_ms))

    return {
        "channel_id": response["id"],
        "resource_id": response["resourceId"],
        "start_page_token": start_page_token,
        "expiration_ms": actual_expiration_ms,
        "expiration_iso": datetime.fromtimestamp(
            actual_expiration_ms / 1000, tz=timezone.utc
        ).isoformat(),
        "watched_folder_id": folder_id,
    }


def stop_webhook(channel_id: str, resource_id: str) -> None:
    service = _service_with_retry()
    service.channels().stop(body={"id": channel_id, "resourceId": resource_id}).execute()


def list_new_pdf_files_since(folder_id: str, page_token: str) -> tuple[list[dict], str]:
    service = _service_with_retry()
    new_files: list[dict] = []
    current_token = page_token

    while True:
        response = (
            service.changes()
            .list(
                pageToken=current_token,
                includeRemoved=False,
                fields=(
                    "nextPageToken, "
                    "newStartPageToken, "
                    "changes(removed, file(id, name, mimeType, parents, trashed))"
                ),
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        for change in response.get("changes", []):
            if change.get("removed"):
                continue

            file_data: dict = change.get("file", {})
            if not file_data.get("mimeType") in SUPPORTED_MIME_TYPES:
                continue
            if file_data.get("trashed"):
                continue

            parents = file_data.get("parents") or []
            if not parents:
                continue

            if folder_id == "root":
                new_files.append(file_data)
                continue

            if folder_id in parents:
                new_files.append(file_data)
                continue

            # If the file is not a direct child, inspect its parent chain recursively.
            parent_chain = parents[:]
            while parent_chain:
                parent_id = parent_chain.pop()
                if parent_id == folder_id:
                    new_files.append(file_data)
                    break

        next_page_token = response.get("nextPageToken")
        if next_page_token:
            current_token = next_page_token
            continue

        current_token = response.get("newStartPageToken", current_token)
        break

    return new_files, current_token


def sync_new_files(all_folders: list[str]) -> list[dict]:
    files: list[dict] = []
    for folder_id in all_folders:
        files.extend(list_pdf_files(folder_id))
    return files
