"""Google Drive sharing permissions utilities."""

import logging
from typing import Any

from slack_sdk import WebClient

from proposal_assistant.drive.client import DriveClient

logger = logging.getLogger(__name__)


def share_with_user(drive: DriveClient, file_id: str, email: str) -> None:
    """Share a file or folder with a user as Editor.

    Args:
        drive: DriveClient instance.
        file_id: Google Drive file or folder ID to share.
        email: Email address of the user to share with.
    """
    drive.share_file(file_id, email, role="writer")
    logger.info("Shared %s with %s as Editor", file_id, email)


def share_with_channel_members(
    drive: DriveClient,
    file_id: str,
    channel_id: str,
    slack_client: WebClient,
) -> list[str]:
    """Share a file or folder with all members of a Slack channel.

    Looks up each channel member's email and shares the file as Editor.
    Members without email addresses are skipped.

    Args:
        drive: DriveClient instance.
        file_id: Google Drive file or folder ID to share.
        channel_id: Slack channel ID to get members from.
        slack_client: Slack WebClient for API calls.

    Returns:
        List of email addresses that were successfully shared with.
    """
    # Get channel members
    members_response = slack_client.conversations_members(channel=channel_id)
    member_ids: list[str] = members_response.get("members", [])

    if not member_ids:
        logger.warning("No members found in channel %s", channel_id)
        return []

    shared_emails: list[str] = []

    for member_id in member_ids:
        try:
            # Look up user info to get email
            user_response = slack_client.users_info(user=member_id)
            user: dict[str, Any] = user_response.get("user", {})
            profile: dict[str, Any] = user.get("profile", {})
            email = profile.get("email")

            if not email:
                logger.debug("No email found for user %s, skipping", member_id)
                continue

            # Skip bot users
            if user.get("is_bot"):
                logger.debug("Skipping bot user %s", member_id)
                continue

            # Share with the user
            share_with_user(drive, file_id, email)
            shared_emails.append(email)

        except Exception as e:
            logger.warning(
                "Failed to share with user %s: %s", member_id, e
            )
            continue

    logger.info(
        "Shared %s with %d channel members from %s",
        file_id,
        len(shared_emails),
        channel_id,
    )
    return shared_emails
