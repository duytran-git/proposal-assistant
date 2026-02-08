"""Google Docs integration module for Proposal Assistant."""

from proposal_assistant.docs.client import DocsClient
from proposal_assistant.docs.deal_analysis import populate_deal_analysis

__all__ = ["DocsClient", "populate_deal_analysis"]
