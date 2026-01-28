"""Parsing utilities for extracting information from filenames."""

from typing import Optional


def extract_client_name(filename: str) -> Optional[str]:
    """Extract client name from a transcript filename.

    Expects filename pattern: "clientname-*.md"
    Extracts everything before the first dash.

    Args:
        filename: The filename to parse (e.g., "acme-meeting-notes.md").

    Returns:
        The client name if pattern matches, None otherwise.

    Examples:
        >>> extract_client_name("acme-corp-meeting.md")
        'acme'
        >>> extract_client_name("clientx-2024-01-notes.md")
        'clientx'
        >>> extract_client_name("invalid.txt")
        None
        >>> extract_client_name("nodash.md")
        None
    """
    # Must be a .md file
    if not filename.lower().endswith(".md"):
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
