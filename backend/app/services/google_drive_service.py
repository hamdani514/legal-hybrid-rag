import io
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from loguru import logger
from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = BACKEND_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class GoogleDriveService:
    """
    Manages Google Drive uploads, downloads, and storage for Verdict AI judgments.
    Target account: verdictaisupport@gmail.com

    Supports:
    1. Service Account authentication (via service_account.json or GOOGLE_APPLICATION_CREDENTIALS)
       with shared Google Drive folder.
    2. OAuth2 User token authentication (via token.json) authorized for verdictaisupport@gmail.com.
    3. Seamless local fallback if credentials have not yet been provided.
    """

    def __init__(self):
        self._service = None
        self._folder_id: Optional[str] = settings.GOOGLE_DRIVE_FOLDER_ID or None
        self._auth_method: Optional[str] = None
        self.target_email = settings.GOOGLE_DRIVE_TARGET_EMAIL

    def _resolve_file_path(self, filepath_or_name: str) -> Optional[Path]:
        if not filepath_or_name:
            return None
        candidate = Path(filepath_or_name)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        # Try relative to backend dir
        backend_candidate = BACKEND_DIR / filepath_or_name
        if backend_candidate.exists():
            return backend_candidate
        # Try relative to repo root
        root_candidate = BACKEND_DIR.parent / filepath_or_name
        if root_candidate.exists():
            return root_candidate
        return None

    def get_service(self):
        """Initializes and returns the Google Drive API client."""
        if self._service is not None:
            return self._service

        if not settings.GOOGLE_DRIVE_ENABLED:
            logger.info("Google Drive is disabled by configuration (GOOGLE_DRIVE_ENABLED=False).")
            return None

        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            # Check 1: User OAuth Token (token.json) for verdictaisupport@gmail.com
            token_path = self._resolve_file_path(settings.GOOGLE_DRIVE_TOKEN_FILE)
            if token_path and token_path.exists():
                logger.info(f"Loading Google Drive user credentials from {token_path}...")
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired Google Drive user credentials...")
                    creds.refresh(Request())
                    with open(token_path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                if creds and creds.valid:
                    self._service = build("drive", "v3", credentials=creds)
                    self._auth_method = "oauth2_user"
                    logger.info(f"✅ Google Drive client initialized via OAuth2 for account: {self.target_email}")
                    return self._service

            # Check 2: Service Account file
            sa_path = self._resolve_file_path(settings.GOOGLE_SERVICE_ACCOUNT_FILE)
            env_sa = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not sa_path and env_sa:
                sa_path = self._resolve_file_path(env_sa)

            if sa_path and sa_path.exists():
                logger.info(f"Loading Google Drive service account credentials from {sa_path}...")
                creds = service_account.Credentials.from_service_account_file(
                    str(sa_path), scopes=SCOPES
                )
                self._service = build("drive", "v3", credentials=creds)
                self._auth_method = "service_account"
                logger.info(f"✅ Google Drive client initialized via Service Account ({creds.service_account_email}) for target: {self.target_email}")
                return self._service

            logger.warning(
                f"⚠️ No Google Drive credentials found (checked {settings.GOOGLE_SERVICE_ACCOUNT_FILE} and {settings.GOOGLE_DRIVE_TOKEN_FILE}). "
                f"Files will use local storage fallback until Google Drive credentials are provided for {self.target_email}."
            )
            return None

        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Drive service: {e}")
            return None

    def is_configured(self) -> bool:
        """Returns True if Google Drive API client is connected."""
        return self.get_service() is not None

    def get_auth_status(self) -> Dict[str, Any]:
        """Returns authentication and configuration status info."""
        configured = self.is_configured()
        return {
            "configured": configured,
            "target_email": self.target_email,
            "auth_method": self._auth_method,
            "folder_id": self._folder_id or "root",
            "service_account_file": settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            "token_file": settings.GOOGLE_DRIVE_TOKEN_FILE,
        }

    def _get_or_create_destination_folder(self) -> Optional[str]:
        """Gets or creates the 'Verdict AI Judgments' folder in Drive."""
        if self._folder_id:
            return self._folder_id

        service = self.get_service()
        if not service:
            return None

        folder_name = "Verdict AI Judgments"
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
            files = results.get("files", [])

            if files:
                self._folder_id = files[0]["id"]
                logger.info(f"Found existing Google Drive folder '{folder_name}' (id: {self._folder_id})")
                return self._folder_id

            # Create folder
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = service.files().create(body=file_metadata, fields="id").execute()
            self._folder_id = folder.get("id")
            logger.info(f"Created new Google Drive folder '{folder_name}' (id: {self._folder_id})")
            return self._folder_id
        except Exception as e:
            logger.error(f"Error checking/creating Drive destination folder: {e}")
            return None

    async def upload_file(
        self,
        file_path: Path | str,
        original_filename: str,
        mime_type: str = "application/pdf",
        description: str = "Verdict AI Ingested Legal Judgment",
    ) -> Dict[str, Any]:
        """
        Uploads an ingested PDF file to Google Drive.
        Returns a dict containing file_id, file_name, web_view_link, etc.
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Source file does not exist: {file_path}")

        file_size = path_obj.stat().st_size
        service = self.get_service()

        # Fallback if Drive is not configured
        if not service:
            logger.warning(
                f"[{original_filename}] Google Drive not configured. Storing with local fallback ID."
            )
            return {
                "file_id": f"local_{path_obj.stem}",
                "file_name": original_filename,
                "mime_type": mime_type,
                "size": file_size,
                "web_view_link": None,
                "web_content_link": None,
                "status": "local_fallback",
                "target_email": self.target_email,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }

        try:
            from googleapiclient.http import MediaFileUpload

            folder_id = self._get_or_create_destination_folder()
            file_metadata: Dict[str, Any] = {
                "name": original_filename,
                "description": description,
                "mimeType": mime_type,
            }
            if folder_id:
                file_metadata["parents"] = [folder_id]

            media = MediaFileUpload(
                str(path_obj),
                mimetype=mime_type,
                resumable=True,
                chunksize=1024 * 1024 * 2,  # 2MB chunks
            )

            logger.info(f"Uploading '{original_filename}' to Google Drive for {self.target_email}...")
            drive_file = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, mimeType, size, webViewLink, webContentLink",
                )
                .execute()
            )

            file_id = drive_file.get("id")
            logger.info(f"✅ Successfully uploaded '{original_filename}' to Google Drive (fileId: {file_id})")

            return {
                "file_id": file_id,
                "file_name": drive_file.get("name", original_filename),
                "mime_type": drive_file.get("mimeType", mime_type),
                "size": int(drive_file.get("size", file_size) or file_size),
                "web_view_link": drive_file.get("webViewLink"),
                "web_content_link": drive_file.get("webContentLink"),
                "folder_id": folder_id,
                "status": "uploaded",
                "target_email": self.target_email,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Failed to upload '{original_filename}' to Google Drive: {e}")
            # Graceful fallback: return local reference
            return {
                "file_id": f"local_{path_obj.stem}",
                "file_name": original_filename,
                "mime_type": mime_type,
                "size": file_size,
                "status": "upload_failed",
                "error": str(e),
                "target_email": self.target_email,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }

    async def download_file_stream(
        self,
        file_id: str,
        fallback_filename: str = "judgment.pdf",
    ) -> Tuple[io.BytesIO, str, str]:
        """
        Retrieves a file by its Drive file_id (or local fallback ID).
        Returns a tuple: (stream, filename, mime_type).
        """
        # Case 1: Local fallback file
        if file_id.startswith("local_"):
            clean_id = file_id.replace("local_", "")
            local_pdf = UPLOADS_DIR / f"{clean_id}.pdf"
            if local_pdf.exists():
                data = local_pdf.read_bytes()
                return io.BytesIO(data), fallback_filename, "application/pdf"

        service = self.get_service()
        if not service:
            # Check if file exists locally in uploads
            local_pdf = UPLOADS_DIR / f"{file_id}.pdf"
            if local_pdf.exists():
                data = local_pdf.read_bytes()
                return io.BytesIO(data), fallback_filename, "application/pdf"
            raise RuntimeError(
                f"Google Drive is not configured and local copy for '{file_id}' was not found."
            )

        try:
            from googleapiclient.http import MediaIoBaseDownload

            # Get metadata for correct filename and mime type
            file_meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
            filename = file_meta.get("name", fallback_filename)
            mime_type = file_meta.get("mimeType", "application/pdf")

            # Stream content
            request = service.files().get_media(fileId=file_id)
            stream = io.BytesIO()
            downloader = MediaIoBaseDownload(stream, request, chunksize=1024 * 1024 * 2)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            stream.seek(0)
            return stream, filename, mime_type

        except Exception as e:
            logger.error(f"Failed to download file {file_id} from Google Drive: {e}")
            # Try local copy as emergency fallback
            local_pdf = UPLOADS_DIR / f"{file_id}.pdf"
            if local_pdf.exists():
                logger.info(f"Serving local copy for {file_id} after Drive retrieval failure.")
                data = local_pdf.read_bytes()
                return io.BytesIO(data), fallback_filename, "application/pdf"
            raise

    async def delete_file(self, file_id: str) -> bool:
        """Deletes a file from Google Drive."""
        if not file_id or file_id.startswith("local_"):
            return False

        service = self.get_service()
        if not service:
            return False

        try:
            service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file {file_id} from Google Drive.")
            return True
        except Exception as e:
            logger.warning(f"Could not delete file {file_id} from Google Drive: {e}")
            return False


google_drive_service = GoogleDriveService()
