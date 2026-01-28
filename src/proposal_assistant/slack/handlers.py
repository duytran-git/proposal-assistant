"""Slack event handlers for Proposal Assistant."""

import logging
from typing import Any

from slack_sdk import WebClient

from proposal_assistant.slack.messages import format_analyzing, format_error

logger = logging.getLogger(__name__)


def handle_analyse_command(
    message: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle the 'Analyse' command with transcript attachment.

    Args:
        message: Slack message event payload.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    thread_ts = message.get("thread_ts") or message.get("ts")
    channel = message.get("channel")
    files = message.get("files", [])

    logger.info(
        "Received Analyse command in channel=%s thread=%s",
        channel,
        thread_ts,
    )

    # Check for file attachments
    if not files:
        error_msg = format_error("INPUT_MISSING")
        say(
            text=error_msg["text"],
            blocks=error_msg["blocks"],
            thread_ts=thread_ts,
        )
        return

    # Acknowledge with "Analyzing..." message
    analyzing_msg = format_analyzing()
    say(
        text=analyzing_msg["text"],
        blocks=analyzing_msg["blocks"],
        thread_ts=thread_ts,
    )

    # TODO: Implement full analysis workflow
    # 1. Validate file extension and content
    # 2. Download transcript
    # 3. Extract client name
    # 4. Create/find client folder
    # 5. Generate deal analysis
    # 6. Post completion message with approval buttons
