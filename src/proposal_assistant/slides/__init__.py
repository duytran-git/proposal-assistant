"""Google Slides integration module for Proposal Assistant."""

from proposal_assistant.slides.client import SlidesClient
from proposal_assistant.slides.proposal_deck import populate_proposal_deck

__all__ = ["SlidesClient", "populate_proposal_deck"]
