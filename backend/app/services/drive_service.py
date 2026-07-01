# # backend/app/services/drive_service.py

# import io
# import os
# import time
# import uuid
# from datetime import datetime, timezone, timedelta
# from functools import lru_cache
# from http.client import IncompleteRead
# from ssl import SSLError

# import httplib2
# from google.auth.exceptions import TransportError
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
# from googleapiclient.http import MediaIoBaseDownload

# from app.config import get_settings

# SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")


# # ---------------------------------------------------------------------------
# # Auth
# # ---------------------------------------------------------------------------

# def _persist_token(creds: Credentials) -> None:
#     with open(TOKEN_PATH, "w") as fh:
#         fh.write(creds.to_json())


# def _get_credentials() -> Credentials:
#     """
#     Credential resolution order:
#       1. token.json valid      → use as-is
#       2. token.json expired    → silent refresh, re-persist
#       3. no token / no refresh → browser consent flow (interactive)

#     Run once interactively to seed token.json:
#         python -c "from app.services.drive_service import _get_drive_service; _get_drive_service()"
#     Subsequent worker runs are fully non-interactive.
#     """
#     settings = get_settings()

#     if not os.path.exists(settings.google_drive_credentials_json):
#         raise FileNotFoundError(
#             f"OAuth credentials file not found: "
#             f"{settings.google_drive_credentials_json!r}\n"
#             "Check GOOGLE_DRIVE_CREDENTIALS_JSON in your .env"
#         )

#     creds: Credentials | None = None

#     if os.path.exists(TOKEN_PATH):
#         creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

#     if creds and creds.valid:
#         return creds

#     if creds and creds.expired and creds.refresh_token:
#         creds.refresh(Request())
#         _persist_token(creds)
#         return creds

#     flow = InstalledAppFlow.from_client_secrets_file(
#         settings.google_drive_credentials_json,
#         SCOPES,
#     )
#     creds = flow.run_local_server(port=0)
#     _persist_token(creds)
#     return creds


# def _build_service():
#     """
#     Build a Drive v3 service from current credentials.

#     googleapiclient manages the HTTP transport internally for OAuth
#     credentials — do NOT pass a custom http= argument, as
#     google.oauth2.credentials.Credentials has no .authorize() method.
#     """
#     return build(
#         "drive",
#         "v3",
#         credentials=_get_credentials(),
#         cache_discovery=False,
#     )


# @lru_cache(maxsize=1)
# def _get_drive_service():
#     """
#     Cached Drive service.

#     Call _get_drive_service.cache_clear() after a 401 so the next
#     call re-authenticates and rebuilds the service cleanly.
#     """
#     return _build_service()


# def _service_with_retry():
#     """
#     Return the cached service, clearing the cache on stale credentials.
#     All public functions use this instead of _get_drive_service() directly.
#     """
#     try:
#         return _get_drive_service()
#     except (TransportError, HttpError):
#         _get_drive_service.cache_clear()
#         return _get_drive_service()


# # ---------------------------------------------------------------------------
# # Public API
# # ---------------------------------------------------------------------------

# def list_pdf_files(folder_id: str) -> list[dict]:
#     """List all non-trashed PDF files in a Drive folder, newest first."""
#     service = _service_with_retry()

#     query = (
#         f"'{folder_id}' in parents "
#         "and mimeType='application/pdf' "
#         "and trashed=false"
#     )

#     response = (
#         service.files()
#         .list(
#             q=query,
#             fields="files(id, name, mimeType, createdTime, modifiedTime)",
#             orderBy="createdTime desc",
#         )
#         .execute()
#     )

#     return response.get("files", [])


# def download_file_bytes(file_id: str, max_retries: int = 5) -> bytes:
#     """
#     Download a Drive file and return its raw bytes.

#     Retries each failed attempt up to max_retries times with
#     exponential back-off (1s, 2s, 4s, 8s, 16s).

#     Handles transient network errors that occur on unstable connections:
#       - SSLError (WRONG_VERSION_NUMBER, DECRYPTION_FAILED, etc.)
#       - IncompleteRead (partial response body)
#       - TimeoutError / ConnectionError
#       - RemoteProtocolError (server disconnected mid-transfer)
#     """
#     _RETRYABLE = (SSLError, IncompleteRead, TimeoutError, ConnectionError, OSError)

#     for attempt in range(max_retries):
#         try:
#             service = _service_with_retry()
#             request = service.files().get_media(fileId=file_id)
#             buffer = io.BytesIO()
#             downloader = MediaIoBaseDownload(
#                 buffer,
#                 request,
#                 chunksize=4 * 1024 * 1024,  # 4 MB chunks
#             )
#             done = False
#             while not done:
#                 _, done = downloader.next_chunk()
#             return buffer.getvalue()

#         except HttpError as exc:
#             # 4xx errors are permanent — don't retry
#             if exc.status_code < 500:
#                 raise
#             if attempt == max_retries - 1:
#                 raise
#             wait = 2 ** attempt
#             print(
#                 f"[drive] Download attempt {attempt + 1} failed "
#                 f"(HttpError {exc.status_code}), retrying in {wait}s…"
#             )

#         except _RETRYABLE as exc:
#             if attempt == max_retries - 1:
#                 raise
#             wait = 2 ** attempt
#             print(
#                 f"[drive] Download attempt {attempt + 1} failed "
#                 f"({type(exc).__name__}: {exc}), retrying in {wait}s…"
#             )

#         # Clear cached service before retry — gets a fresh connection
#         _get_drive_service.cache_clear()
#         time.sleep(wait)

#     raise RuntimeError(f"Download failed after {max_retries} attempts: {file_id}")


# def get_file_metadata(file_id: str) -> dict:
#     """Retrieve id, name, mimeType, createdTime, modifiedTime for a file."""
#     service = _service_with_retry()

#     return (
#         service.files()
#         .get(
#             fileId=file_id,
#             fields="id, name, mimeType, createdTime, modifiedTime",
#         )
#         .execute()
#     )


# def register_webhook(folder_id: str, webhook_url: str) -> dict:
#     """
#     Register a push-notification channel on the Drive changes feed.

#     Watches the entire Drive changes feed — the webhook handler must
#     filter events by folder_id itself.

#     Returns channel metadata needed to stop or renew the channel.
#     """
#     service = _service_with_retry()

#     start_page_token: str = (
#         service.changes().getStartPageToken().execute()["startPageToken"]
#     )

#     channel_id = str(uuid.uuid4())
#     expiration_ms = int(
#         (datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000
#     )

#     response = (
#         service.changes()
#         .watch(
#             pageToken=start_page_token,
#             body={
#                 "id": channel_id,
#                 "type": "web_hook",
#                 "address": webhook_url,
#                 "expiration": expiration_ms,
#             },
#         )
#         .execute()
#     )

#     actual_expiration_ms = int(response.get("expiration", expiration_ms))

#     return {
#         "channel_id": response["id"],
#         "resource_id": response["resourceId"],
#         "start_page_token": start_page_token,
#         "expiration_ms": actual_expiration_ms,
#         "expiration_iso": datetime.fromtimestamp(
#             actual_expiration_ms / 1000, tz=timezone.utc
#         ).isoformat(),
#         "watched_folder_id": folder_id,
#     }


# def stop_webhook(channel_id: str, resource_id: str) -> None:
#     """Stop an active push-notification channel."""
#     service = _service_with_retry()

#     service.channels().stop(
#         body={"id": channel_id, "resourceId": resource_id}
#     ).execute()


# def list_new_pdf_files_since(
#     folder_id: str,
#     page_token: str,
# ) -> tuple[list[dict], str]:
#     """
#     Walk the Drive changes feed from page_token forward.

#     Filters to non-trashed PDF files whose parents include folder_id.

#     Returns:
#         (new_pdf_files, next_page_token)
#         Persist next_page_token for the following webhook call.
#     """
#     service = _service_with_retry()

#     new_files: list[dict] = []
#     current_token = page_token

#     while True:
#         response = (
#             service.changes()
#             .list(
#                 pageToken=current_token,
#                 includeRemoved=False,
#                 fields=(
#                     "nextPageToken, "
#                     "newStartPageToken, "
#                     "changes(removed, file(id, name, mimeType, parents, trashed))"
#                 ),
#             )
#             .execute()
#         )

#         for change in response.get("changes", []):
#             if change.get("removed"):
#                 continue

#             file_data: dict = change.get("file", {})

#             if (
#                 file_data.get("mimeType") == "application/pdf"
#                 and not file_data.get("trashed")
#                 and folder_id in (file_data.get("parents") or [])
#             ):
#                 new_files.append(file_data)

#         next_page_token = response.get("nextPageToken")
#         if next_page_token:
#             current_token = next_page_token
#             continue

#         current_token = response.get("newStartPageToken", current_token)
#         break

#     return new_files, current_token
# backend/app/services/drive_service.py

import io
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from http.client import IncompleteRead
from ssl import SSLError

import httplib2
from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import get_settings

# =========================================================
# CONFIGURATION MISE À JOUR
# =========================================================

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")

# Ajout des types MIME pour supporter Word et Images en plus du PDF
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
    "application/msword", # .doc
    "image/png",
    "image/jpeg",
    "image/webp"
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _persist_token(creds: Credentials) -> None:
    with open(TOKEN_PATH, "w") as fh:
        fh.write(creds.to_json())

def _get_credentials() -> Credentials:
    """
    Gestion des credentials Google avec rafraîchissement automatique.
    """
    # Votre logique d'auth existante reste inchangée
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist_token(creds)
    return creds

# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------

def sync_new_files(all_folders: list[str]) -> list[dict]:
    """
    Scanne les dossiers Google Drive configurés et détecte les nouveaux fichiers
    parmi les formats PDF, Word et Images supportés.
    """
    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)
    new_files = []
    current_token = None

    # Boucle de pagination pour récupérer les changements
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
                includeItemsFromAllDrives=True
            )
            .execute()
        )

        for change in response.get("changes", []):
            if change.get("removed"):
                continue

            file_data: dict = change.get("file", {})\
            mime = file_data.get("mimeType")
            parents = file_data.get("parents") or []

            # Validation du format (Désormais compatible Word/Image)
            # et de l'appartenance aux dossiers surveillés
            is_valid_mime = mime in SUPPORTED_MIME_TYPES
            is_in_monitored_folders = any(p_id in all_folders for p_id in parents)

            if (
                is_valid_mime
                and not file_data.get("trashed")
                and is_in_monitored_folders
            ):
                new_files.append(file_data)

        next_page_token = response.get("nextPageToken")
        if next_page_token:
            current_token = next_page_token
            continue
        break
        
    return new_files