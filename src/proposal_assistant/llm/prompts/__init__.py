"""LLM prompt templates for Proposal Assistant."""

from proposal_assistant.llm.prompts.deal_analysis import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    format_user_prompt,
)
from proposal_assistant.llm.prompts.proposal_deck import (
    SYSTEM_PROMPT as PROPOSAL_DECK_SYSTEM_PROMPT,
    USER_TEMPLATE as PROPOSAL_DECK_USER_TEMPLATE,
    format_user_prompt as format_proposal_deck_prompt,
)

__all__ = [
    # Deal Analysis prompts
    "SYSTEM_PROMPT",
    "USER_TEMPLATE",
    "format_user_prompt",
    # Proposal Deck prompts
    "PROPOSAL_DECK_SYSTEM_PROMPT",
    "PROPOSAL_DECK_USER_TEMPLATE",
    "format_proposal_deck_prompt",
]
