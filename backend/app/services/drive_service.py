# app/services/drive_service.py
import uuid
import io
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


# FIX 1 — Cache the service instance per worker process.
# Previously, every call to any drive_service function rebuilt credentials
# from disk and called build(), costing ~50-100ms and a file read each time.
# lru_cache(maxsize=1) gives one shared instance per process; credentials
# don't change at runtime so there is no stale-data risk.
@lru_cache(maxsize=1)
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


# FIX 2 — Watch the changes feed, not files().watch(fileId=folder_id).
#
# The old code called:
#   service.files().watch(fileId=folder_id, body=body)
#
# That registers a push notification for changes TO the folder object itself
# (rename, permission changes, trashing) — not for new files added inside it.
# To detect new children, you must watch the Drive changes feed and filter
# server-side or client-side for files whose parent is your folder.
#
# The correct approach uses changes().getStartPageToken() to snapshot the
# current state, then changes().watch() to receive push notifications for
# anything that moves the change cursor forward.  In your webhook handler
# you call changes().list(pageToken=...) to enumerate what changed and
# filter for new PDFs under folder_id.
#
# This function now returns the startPageToken alongside the channel info
# so your webhook_manager can persist it and pass it to changes().list().
def register_webhook(folder_id: str, webhook_url: str) -> dict:
    service = _get_drive_service()

    # Snapshot the current change cursor so we only receive events from now on.
    token_resp = service.changes().getStartPageToken().execute()
    start_page_token = token_resp["startPageToken"]

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

    # Watch the changes feed, not a specific file.
    response = (
        service.changes()
        .watch(pageToken=start_page_token, body=body)
        .execute()
    )

    return {
        "channel_id": response["id"],
        "resource_id": response["resourceId"],
        "start_page_token": start_page_token,   # persist this in your DB / settings
        "expiration_ms": int(response.get("expiration", expiration_ms)),
        "expiration_iso": datetime.fromtimestamp(
            int(response.get("expiration", expiration_ms)) / 1000,
            tz=timezone.utc,
        ).isoformat(),
        # Remember which folder to filter on when changes arrive.
        "watched_folder_id": folder_id,
    }


def stop_webhook(channel_id: str, resource_id: str) -> None:
    service = _get_drive_service()
    service.channels().stop(
        body={"id": channel_id, "resourceId": resource_id}
    ).execute()


# NEW — Call this from your webhook handler after receiving a push notification.
# Enumerates changed files since page_token and returns only new PDFs that
# live directly inside folder_id.  Persist the returned next_page_token so
# the next invocation picks up where this one left off.
def list_new_pdf_files_since(folder_id: str, page_token: str) -> tuple[list[dict], str]:
    """
    Returns (new_pdf_files, next_page_token).

    new_pdf_files: list of file metadata dicts for PDFs added to folder_id
                   since page_token.
    next_page_token: persist this and pass it on the next call.
    """
    service = _get_drive_service()
    new_files: list[dict] = []
    next_token = page_token

    while True:
        resp = (
            service.changes()
            .list(
                pageToken=next_token,
                fields=(
                    "nextPageToken, newStartPageToken,"
                    " changes(removed, file(id, name, mimeType, parents, trashed))"
                ),
                includeRemoved=False,
            )
            .execute()
        )

        for change in resp.get("changes", []):
            if change.get("removed"):
                continue
            f = change.get("file", {})
            if (
                not f.get("trashed")
                and f.get("mimeType") == "application/pdf"
                and folder_id in (f.get("parents") or [])
            ):
                new_files.append(f)

        if "nextPageToken" in resp:
            next_token = resp["nextPageToken"]
        else:
            # newStartPageToken marks the end of the change log — persist this.
            next_token = resp.get("newStartPageToken", next_token)
            break

    return new_files, next_token