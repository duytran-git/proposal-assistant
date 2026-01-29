"""Slack message formatting utilities using Block Kit."""

from typing import Any

# Error type to user-friendly message mapping (from docs/technical-design.md Appendix A)
ERROR_MESSAGES: dict[str, str] = {
    "INPUT_MISSING": "Please attach a meeting transcript (.md file)",
    "INPUT_INVALID": "Transcript file appears empty or invalid",
    "LANGUAGE_UNSUPPORTED": "Only English transcripts supported",
    "DRIVE_PERMISSION": "Unable to access client folder",
    "DRIVE_QUOTA": "Drive temporarily unavailable",
    "DOCS_ERROR": "Failed to create Deal Analysis",
    "SLIDES_ERROR": "Failed to create proposal deck",
    "LLM_ERROR": "AI service temporarily unavailable",
    "LLM_INVALID": "Unable to generate analysis",
    "LLM_OFFLINE": "Local AI unavailable. Use cloud?",
    "APPROVAL_UNCLEAR": "Please reply 'Yes' or 'No'",
    "STATE_MISSING": "Lost track. Please start over",
}

DEFAULT_ERROR_MESSAGE = "An unexpected error occurred"


def format_analyzing() -> dict[str, Any]:
    """Format the 'analyzing transcript' status message.

    Returns:
        Slack Block Kit message dict with analyzing status.
    """
    return {
        "text": "Analyzing transcript...",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *Analyzing transcript...*",
                },
            }
        ],
    }


def format_deal_analysis_complete(
    link: str, missing_items: list[str]
) -> dict[str, Any]:
    """Format the deal analysis completion message.

    Args:
        link: URL to the created Deal Analysis document.
        missing_items: List of missing information items identified.

    Returns:
        Slack Block Kit message dict with doc link and missing items.
    """
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":white_check_mark: *Deal Analysis created*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"<{link}|View Deal Analysis>"},
        },
    ]

    if missing_items:
        items_text = "\n".join(f"• {item}" for item in missing_items)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Missing information:*\n{items_text}",
                },
            }
        )

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Should I continue and create a draft proposal deck?",
            },
        }
    )

    return {
        "text": "Deal Analysis created",
        "blocks": blocks,
    }


def format_approval_buttons() -> dict[str, Any]:
    """Format the approval Yes/No interactive buttons.

    Returns:
        Slack Block Kit actions block with approval buttons.
    """
    return {
        "type": "actions",
        "block_id": "approval_actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Yes", "emoji": True},
                "style": "primary",
                "action_id": "approve_deck",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "No", "emoji": True},
                "style": "danger",
                "action_id": "reject_deck",
            },
        ],
    }


def format_generating_deck() -> dict[str, Any]:
    """Format the 'generating proposal deck' status message.

    Returns:
        Slack Block Kit message dict with generating status.
    """
    return {
        "text": "Generating proposal deck...",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *Generating proposal deck...*",
                },
            }
        ],
    }


def format_regenerating(version: int) -> dict[str, Any]:
    """Format the 'regenerating deal analysis' status message.

    Args:
        version: The version number being generated.

    Returns:
        Slack Block Kit message dict with regenerating status.
    """
    return {
        "text": f"Regenerating Deal Analysis (v{version})...",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":arrows_counterclockwise: *Regenerating Deal Analysis (v{version})...*",
                },
            }
        ],
    }


def format_deck_complete(link: str) -> dict[str, Any]:
    """Format the proposal deck completion message.

    Args:
        link: URL to the created Proposal Deck presentation.

    Returns:
        Slack Block Kit message dict with deck link.
    """
    return {
        "text": "Proposal deck created",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":white_check_mark: *Proposal deck created*",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{link}|View Proposal Deck>",
                },
            },
        ],
    }


def format_rejection_confirmed() -> dict[str, Any]:
    """Format the rejection confirmation message.

    Returns:
        Slack Block Kit message dict confirming rejection.
    """
    return {
        "text": "Got it, no proposal deck will be created.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":ok_hand: Got it, no proposal deck will be created.",
                },
            }
        ],
    }


def format_fetch_failures(failed_urls: list[str]) -> dict[str, Any]:
    """Format a warning message for URLs that could not be fetched.

    Args:
        failed_urls: List of URLs that failed to fetch.

    Returns:
        Slack Block Kit message dict with warning about failed URLs.
    """
    urls_text = ", ".join(failed_urls)
    return {
        "text": f"Could not fetch: {urls_text}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":warning: Could not fetch: {urls_text}",
                },
            }
        ],
    }


def format_error(error_type: str) -> dict[str, Any]:
    """Format a user-friendly error message.

    Args:
        error_type: Error type code (e.g., "INPUT_MISSING", "LLM_ERROR").

    Returns:
        Slack Block Kit message dict with error message.
    """
    message = ERROR_MESSAGES.get(error_type, DEFAULT_ERROR_MESSAGE)

    return {
        "text": message,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":x: {message}"},
            }
        ],
    }
