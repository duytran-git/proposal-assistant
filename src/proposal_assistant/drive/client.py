"""Google Drive API client for Proposal Assistant."""

import io
import json
import logging
from typing import Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from proposal_assistant.config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

class DriveClient:
    """Google Drive API wrapper using service account authentication."""

    def __init__(self, config: Config) -> None:
        credentials = Credentials.from_service_account_info(
            json.loads(config.google_service_account_json),
            scopes=SCOPES,
        )
        self._service = build("drive", "v3", credentials=credentials)
        self._root_folder_id = config.google_drive_root_folder_id

    def find_folder(self, parent_id: str, folder_name: str) -> Optional[str]:
        """Find folder by name under parent.

        Args:
            parent_id: ID of the parent folder to search in.
            folder_name: Name of the folder to find.

        Returns:
            Folder ID if found, None otherwise.
        """
        query = (
            f"name = '{folder_name}' "
            f"and '{parent_id}' in parents "
            f"and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        response = (
            self._service.files()
            .list(q=query, fields="files(id)", pageSize=1)
            .execute()
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def create_folder(self, parent_id: str, folder_name: str) -> str:
        """Create folder under parent.

        Args:
            parent_id: ID of the parent folder.
            folder_name: Name for the new folder.

        Returns:
            ID of the newly created folder.
        """
        metadata: dict[str, Any] = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = (
            self._service.files()
            .create(body=metadata, fields="id")
            .execute()
        )
        logger.info("Created folder '%s' with id=%s", folder_name, folder["id"])
        return folder["id"]

    def download_file(self, file_id: str) -> bytes:
        """Download file content by ID.

        Args:
            file_id: Google Drive file ID.

        Returns:
            File content as bytes.
        """
        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        return buffer.getvalue()

    def share_file(
        self, file_id: str, email: str, role: str = "writer"
    ) -> None:
        """Share file with user email.

        Args:
            file_id: Google Drive file ID.
            email: Email address to share with.
            role: Permission role (default: "writer").
        """
        permission: dict[str, str] = {
            "type": "user",
            "role": role,
            "emailAddress": email,
        }
        self._service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=False,
        ).execute()
        logger.info("Shared file %s with %s as %s", file_id, email, role)
