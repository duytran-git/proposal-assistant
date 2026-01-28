"""Slack integration module for Proposal Assistant."""

from proposal_assistant.slack.handlers import handle_analyse_command
from proposal_assistant.slack.messages import (
    format_analyzing,
    format_approval_buttons,
    format_deal_analysis_complete,
    format_error,
)

__all__ = [
    "format_analyzing",
    "format_approval_buttons",
    "format_deal_analysis_complete",
    "format_error",
    "handle_analyse_command",
]
