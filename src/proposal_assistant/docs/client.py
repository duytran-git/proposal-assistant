"""Google Docs API client for Proposal Assistant."""

import json
import logging
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from proposal_assistant.config import Config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


class DocsClient:
    """Google Docs API wrapper using service account authentication.

    Uses Drive API for document creation in specific folders and
    Docs API for content manipulation.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the Docs client.

        Args:
            config: Application configuration with Google credentials.
        """
        credentials = Credentials.from_service_account_info(
            json.loads(config.google_service_account_json),
            scopes=SCOPES,
        )
        self._docs_service = build("docs", "v1", credentials=credentials)
        self._drive_service = build("drive", "v3", credentials=credentials)

    def create_document(self, title: str, folder_id: str) -> tuple[str, str]:
        """Create a new Google Doc in the specified folder.

        Uses the Drive API to create the document directly in the
        target folder with the Google Docs MIME type.

        Args:
            title: Title for the new document.
            folder_id: Google Drive folder ID to create the document in.

        Returns:
            Tuple of (document_id, web_view_link).
        """
        metadata: dict[str, Any] = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        }
        doc = (
            self._drive_service.files()
            .create(body=metadata, fields="id,webViewLink")
            .execute()
        )
        doc_id = doc["id"]
        web_link = doc["webViewLink"]
        logger.info("Created document '%s' with id=%s", title, doc_id)
        return doc_id, web_link
