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
from typing import Any, List, Dict, Tuple

import httplib2
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

# Formats de documents officiellement pris en charge par l'ATS d'Atihmam
SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.google-apps.document": "gdoc",       # Sera exporté au format PDF lors du téléchargement
    "application/vnd.google-apps.shortcut": "shortcut"    # Sera résolu vers le fichier cible d'origine
}

# ---------------------------------------------------------------------------
# Authentification & Sessions API
# ---------------------------------------------------------------------------

def _persist_token(creds: Credentials) -> None:
    """Enregistre les informations d'identification locales dans token.json."""
    with open(TOKEN_PATH, "w") as fh:
        fh.write(creds.to_json())


def _get_credentials() -> Credentials:
    """
    Résout les autorisations OAuth de l'application.
    Lit les configurations globales pour localiser les secrets d'authentification.
    """
    settings = get_settings()

    if not os.path.exists(settings.google_drive_credentials_json):
        raise FileNotFoundError(
            f"Fichier de configuration OAuth introuvable : "
            f"{settings.google_drive_credentials_json!r}\n"
            "Veuillez configurer GOOGLE_DRIVE_CREDENTIALS_JSON dans votre .env"
        )

    creds: Credentials | None = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist_token(creds)
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(
        settings.google_drive_credentials_json,
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _persist_token(creds)
    return creds


def _build_service():
    """Construit un client de connexion d'API Google Drive v3."""
    return build(
        "drive",
        "v3",
        credentials=_get_credentials(),
        cache_discovery=False,
    )


@lru_cache(maxsize=1)
def _get_drive_service():
    """Met en cache l'instance du service client Google Drive."""
    return _build_service()


def _service_with_retry():
    """
    Récupère le client en cache ou reconstruit la session
    en cas d'expiration ou d'erreur de transport d'API.
    """
    try:
        return _get_drive_service()
    except (TransportError, HttpError):
        _get_drive_service.cache_clear()
        return _get_drive_service()


# ---------------------------------------------------------------------------
# Analyse Récursive de l'Arborescence (Avec Pagination & Support Drives d'équipe)
# ---------------------------------------------------------------------------

def _get_subfolders(service: Any, parent_id: str) -> List[str]:
    """
    Parcourt récursivement tous les niveaux de répertoires à partir d'un parent
    pour lister l'ensemble des identifiants de sous-dossiers.
    Gère la pagination Google Drive et les dossiers partagés d'équipe.
    """
    subfolders = [parent_id]
    query = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    page_token = None
    
    try:
        while True:
            response = service.files().list(
                q=query, 
                fields="nextPageToken, files(id)",
                pageToken=page_token,
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            for f in response.get("files", []):
                # Descente récursive pour lister les sous-dossiers enfants
                subfolders.extend(_get_subfolders(service, f["id"]))
                
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        print(f"[drive] Erreur lors de la récupération des dossiers enfants de {parent_id}: {e}")
        
    return list(set(subfolders))


# ---------------------------------------------------------------------------
# API Publique d'Ingestion
# ---------------------------------------------------------------------------

def list_pdf_files(folder_id: str) -> List[Dict[str, Any]]:
    """
    Parcourt récursivement le dossier cible et extrait tous les fichiers
    compatibles (PDF, Word, Google Docs) pour leur traitement.
    Maintient le nom de fonction historique pour des raisons de compatibilité.
    """
    service = _service_with_retry()
    
    print("[drive] [SUIVI] Analyse récursive de tous les dossiers de votre Google Drive en cours...")
    
    # Récupère l'intégralité de l'arborescence des dossiers (correction récursive)
    folders = _get_subfolders(service, folder_id)
    all_files = []
    
    # Nous découpons la liste des dossiers par paquets de 25 pour éviter l'erreur de requête HTTP 400 (Query too complex)
    folder_chunks = [folders[i:i + 25] for i in range(0, len(folders), 25)]
    
    mime_queries = " or ".join([
        f"mimeType='{mtype}'" 
        for mtype in SUPPORTED_MIME_TYPES.keys() 
        if mtype != "application/vnd.google-apps.shortcut"
    ])
    
    for chunk in folder_chunks:
        parent_queries = " or ".join([f"'{fid}' in parents" for fid in chunk])
        query = f"({parent_queries}) and ({mime_queries}) and trashed=false"
        page_token = None
        
        try:
            # Boucle de pagination illimitée pour récupérer TOUS les fichiers du groupe de dossiers
            while True:
                response = (
                    service.files()
                    .list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime)",
                        orderBy="createdTime desc",
                        pageToken=page_token,
                        pageSize=100,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True
                    )
                    .execute()
                )
                all_files.extend(response.get("files", []))
                
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except Exception as e:
            print(f"[drive] Erreur d'appel API sur un groupe de dossiers : {e}")
            
    print(f"[drive] [SUIVI] Analyse terminée : {len(all_files)} fichiers éligibles trouvés au total.")
    return all_files


def download_file_bytes(file_id: str, max_retries: int = 5) -> bytes:
    """
    Télécharge et extrait les octets bruts d'un document.
    Si le document est un Google Doc natif, il est automatiquement converti
    au format PDF à la volée. Résout également les raccourcis.
    """
    _RETRYABLE = (SSLError, IncompleteRead, TimeoutError, ConnectionError, OSError)

    for attempt in range(max_retries):
        try:
            service = _service_with_retry()
            
            # Récupération préalable des métadonnées du fichier (avec support des Drives partagés)
            meta = service.files().get(
                fileId=file_id, 
                fields="name, mimeType, shortcutDetails",
                supportsAllDrives=True
            ).execute()
            mime_type = meta.get("mimeType")
            file_name = meta.get("name", "Fichier sans nom")
            
            # Résolution de raccourci Google Drive
            if mime_type == "application/vnd.google-apps.shortcut":
                target_id = meta.get("shortcutDetails", {}).get("targetId")
                if target_id:
                    return download_file_bytes(target_id, max_retries)
                else:
                    raise ValueError("Le raccourci cible est introuvable ou cassé.")

            print(f"[drive] [SUIVI] Téléchargement en cours : '{file_name}' ({mime_type})...")

            # Conversion dynamique ou téléchargement standard
            if mime_type == "application/vnd.google-apps.document":
                # Exportation et conversion de Google Doc en PDF à la volée
                request = service.files().export_media(fileId=file_id, mimeType="application/pdf")
            else:
                # Lecture standard pour les fichiers PDF et Microsoft Word binaires
                request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(
                buffer,
                request,
                chunksize=4 * 1024 * 1024,  # Chunks de 4 Mo pour l'efficacité
            )
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            print(f"[drive] [SUIVI] Téléchargement réussi : '{file_name}' ({len(buffer.getvalue())} octets).")
            return buffer.getvalue()

        except HttpError as exc:
            # Erreurs HTTP client (4xx) : échec définitif direct
            if exc.status_code < 500:
                raise
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(
                f"[drive] Échec de téléchargement {attempt + 1} (HttpError {exc.status_code}), "
                f"nouvel essai dans {wait}s…"
            )

        except _RETRYABLE as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(
                f"[drive] Échec de téléchargement {attempt + 1} "
                f"({type(exc).__name__}: {exc}), nouvel essai dans {wait}s…"
            )

        # Vide le cache avant de réessayer pour initialiser une session neuve
        _get_drive_service.cache_clear()
        time.sleep(wait)

    raise RuntimeError(f"Échec définitif du téléchargement de {file_id} après {max_retries} tentatives.")


def get_file_metadata(file_id: str) -> dict:
    """Récupère l'id, le nom, le type de fichier, et les dates d'un document."""
    service = _service_with_retry()

    return (
        service.files()
        .get(
            fileId=file_id,
            fields="id, name, mimeType, createdTime, modifiedTime",
            supportsAllDrives=True
        )
        .execute()
    )


def register_webhook(folder_id: str, webhook_url: str) -> dict:
    """Enregistre un canal d'écoute d'événements (Push notifications) sur le Drive."""
    service = _service_with_retry()

    start_page_token: str = (
        service.changes().getStartPageToken().execute()["startPageToken"]
    )

    channel_id = str(uuid.uuid4())
    expiration_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000
    )

    response = (
        service.changes()
        .watch(
            pageToken=start_page_token,
            body={
                "id": channel_id,
                "type": "web_hook",
                "address": webhook_url,
                "expiration": expiration_ms,
            },
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        )
        .execute()
    )

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
    """Arrête un canal d'écoute de changements actif."""
    service = _service_with_retry()

    service.channels().stop(
        body={"id": channel_id, "resourceId": resource_id}
    ).execute()


def list_new_pdf_files_since(
    folder_id: str,
    page_token: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Parcourt le journal des modifications depuis le jeton de page fourni.
    Filtre les fichiers non-supprimés pour ne retenir que les formats supportés
    qui se trouvent dans l'arborescence des dossiers surveillés.
    """
    service = _service_with_retry()
    all_folders = _get_subfolders(service, folder_id)

    new_files: List[Dict[str, Any]] = []
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
                includeItemsFromAllDrives=True
            )
            .execute()
        )

        for change in response.get("changes", []):
            if change.get("removed"):
                continue

            file_data: dict = change.get("file", {})
            mime = file_data.get("mimeType")
            parents = file_data.get("parents") or []

            # Validation du format et de l'appartenance à l'un des dossiers gérés
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

        current_token = response.get("newStartPageToken", current_token)
        break

    return new_files, current_token