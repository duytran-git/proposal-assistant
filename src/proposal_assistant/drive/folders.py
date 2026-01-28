"""Folder navigation and creation logic for Google Drive."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proposal_assistant.drive.client import DriveClient

logger = logging.getLogger(__name__)

# Subfolder name → result dict key
CLIENT_SUBFOLDERS: dict[str, str] = {
    "Meetings": "meetings_folder_id",
    "Analyse here": "analyse_folder_id",
    "Proposals": "proposals_folder_id",
    "References": "references_folder_id",
}


def get_or_create_client_folder(
    drive: "DriveClient", client_name: str
) -> dict[str, str]:
    """Ensure full client folder structure exists.

    Creates the client folder and subfolders (Meetings, Analyse here,
    Proposals, References) under the root Drive folder if they don't
    already exist.

    Args:
        drive: DriveClient instance for API calls.
        client_name: Name of the client.

    Returns:
        Dict with folder IDs::

            {
                "client_folder_id": str,
                "meetings_folder_id": str,
                "analyse_folder_id": str,
                "proposals_folder_id": str,
                "references_folder_id": str,
            }
    """
    root_id = drive._root_folder_id

    # Find or create client root folder
    client_folder_id = drive.find_folder(root_id, client_name)
    if not client_folder_id:
        client_folder_id = drive.create_folder(root_id, client_name)

    result: dict[str, str] = {"client_folder_id": client_folder_id}

    for folder_name, key in CLIENT_SUBFOLDERS.items():
        folder_id = drive.find_folder(client_folder_id, folder_name)
        if not folder_id:
            folder_id = drive.create_folder(client_folder_id, folder_name)
        result[key] = folder_id

    return result
