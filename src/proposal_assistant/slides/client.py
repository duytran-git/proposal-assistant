"""Google Slides API client for Proposal Assistant."""

import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from proposal_assistant.config import Config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]


class SlidesClient:
    """Google Slides API wrapper using service account authentication.

    Uses Drive API for template duplication and Slides API for
    presentation reading and content manipulation.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the Slides client.

        Args:
            config: Application configuration with Google credentials.
        """
        credentials = Credentials.from_service_account_info(
            json.loads(config.google_service_account_json),
            scopes=SCOPES,
        )
        self._slides_service = build("slides", "v1", credentials=credentials)
        self._drive_service = build("drive", "v3", credentials=credentials)
        self._template_id = config.proposal_template_slide_id
        self._template_path = config.proposal_template_path

    def duplicate_template(self, title: str, folder_id: str) -> tuple[str, str]:
        """Create a new presentation from the template in a target folder.

        Prefers uploading the local PPTX template with auto-conversion to
        Google Slides. Falls back to copying an existing Slides template by ID
        if no local file is available.

        Args:
            title: Title for the new presentation.
            folder_id: Google Drive folder ID to place the copy in.

        Returns:
            Tuple of (presentation_id, web_view_link).
        """
        local_path = Path(self._template_path)
        if local_path.is_file():
            return self._upload_template(title, folder_id, local_path)
        if self._template_id:
            return self._copy_template(title, folder_id)
        raise FileNotFoundError(
            f"No template available: local path '{self._template_path}' not found "
            f"and PROPOSAL_TEMPLATE_SLIDE_ID is not set."
        )

    def _upload_template(self, title: str, folder_id: str, local_path: Path) -> tuple[str, str]:
        """Upload a local PPTX file and convert it to Google Slides."""
        file_metadata = {
            "name": title,
            "parents": [folder_id],
            "mimeType": "application/vnd.google-apps.presentation",
        }
        media = MediaFileUpload(
            str(local_path),
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resumable=True,
        )
        result = (
            self._drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        presentation_id = result["id"]
        web_link = result["webViewLink"]
        logger.info(
            "Uploaded template '%s' as '%s' (id=%s)",
            local_path,
            title,
            presentation_id,
        )
        return presentation_id, web_link

    def _copy_template(self, title: str, folder_id: str) -> tuple[str, str]:
        """Copy an existing Google Slides template by ID."""
        copy = (
            self._drive_service.files()
            .copy(
                fileId=self._template_id,
                body={"name": title, "parents": [folder_id]},
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        presentation_id = copy["id"]
        web_link = copy["webViewLink"]
        logger.info(
            "Copied template '%s' as '%s' (id=%s)",
            self._template_id,
            title,
            presentation_id,
        )
        return presentation_id, web_link

    def get_layout_by_name(self, presentation_id: str, layout_name: str) -> str | None:
        """Get a slide layout object ID by its display name.

        Args:
            presentation_id: Google Slides presentation ID.
            layout_name: Layout display name (e.g. "TITLE_AND_BODY").

        Returns:
            Layout object ID if found, None otherwise.
        """
        presentation: dict[str, Any] = (
            self._slides_service.presentations()
            .get(
                presentationId=presentation_id,
                fields="layouts(objectId,layoutProperties.displayName)",
            )
            .execute()
        )
        for layout in presentation.get("layouts", []):
            display_name = layout.get("layoutProperties", {}).get("displayName", "")
            if display_name == layout_name:
                return layout["objectId"]
        return None
