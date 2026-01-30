"""Google Slides API client for Proposal Assistant."""

import json
import logging
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from proposal_assistant.config import Config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
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

    def duplicate_template(self, title: str, folder_id: str) -> tuple[str, str]:
        """Duplicate the proposal template into a target folder.

        Copies the configured template presentation via the Drive API,
        then moves it into the specified folder.

        Args:
            title: Title for the new presentation.
            folder_id: Google Drive folder ID to place the copy in.

        Returns:
            Tuple of (presentation_id, web_view_link).
        """
        copy = (
            self._drive_service.files()
            .copy(
                fileId=self._template_id,
                body={"name": title, "parents": [folder_id]},
                fields="id,webViewLink",
            )
            .execute()
        )
        presentation_id = copy["id"]
        web_link = copy["webViewLink"]
        logger.info(
            "Duplicated template '%s' as '%s' (id=%s)",
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
