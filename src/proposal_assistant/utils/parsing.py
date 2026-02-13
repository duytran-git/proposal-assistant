"""Parsing utilities for extracting information from filenames."""

from typing import Optional

from proposal_assistant.constants import SUPPORTED_TRANSCRIPT_EXTENSIONS


def extract_client_name(filename: str) -> Optional[str]:
    """Extract client name from a transcript filename.

    Expects filename pattern: "clientname-*.<ext>"
    Extracts everything before the first dash.

    Args:
        filename: The filename to parse (e.g., "acme-meeting-notes.md").

    Returns:
        The client name if pattern matches, None otherwise.

    Examples:
        >>> extract_client_name("acme-corp-meeting.md")
        'acme'
        >>> extract_client_name("clientx-2024-01-notes.txt")
        'clientx'
        >>> extract_client_name("acme-proposal.docx")
        'acme'
        >>> extract_client_name("invalid.pdf")
        None
        >>> extract_client_name("nodash.md")
        None
    """
    # Must be a supported transcript file
    if not filename.lower().endswith(SUPPORTED_TRANSCRIPT_EXTENSIONS):
        return None

    # Must contain a dash
    if "-" not in filename:
        return None

    # Extract everything before the first dash
    client_name = filename.split("-", 1)[0]

    # Return None if empty
    if not client_name:
        return None

    return client_name
