"""Google Drive integration module for Proposal Assistant."""

from proposal_assistant.drive.client import DriveClient
from proposal_assistant.drive.folders import get_or_create_client_folder

__all__ = ["DriveClient", "get_or_create_client_folder"]
