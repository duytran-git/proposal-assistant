"""MCP server setup for Proposal Assistant.

Bundles all custom MCP tools into an in-process server that the
Claude Agent SDK client can use during agentic workflows.
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server

from proposal_assistant.llm.tools import (
    create_client_folder,
    create_deal_analysis,
    create_proposal_deck,
    share_document,
)


def get_proposal_mcp_server():
    """Create and return the Proposal Assistant MCP server.

    Returns an in-process MCP server with all Google Drive/Docs/Slides
    tools registered for autonomous use by the Claude Agent SDK.
    """
    return create_sdk_mcp_server(
        name="proposal-assistant",
        version="1.0.0",
        tools=[
            create_client_folder,
            create_deal_analysis,
            create_proposal_deck,
            share_document,
        ],
    )
