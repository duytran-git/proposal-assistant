"""MCP tool definitions for Claude Agent SDK.

Each tool wraps existing Google Drive/Docs/Slides operations so the
Claude Agent SDK can invoke them autonomously during agentic workflows.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)


def _ok(text: str) -> dict[str, Any]:
    """Return MCP-compatible success response."""
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict[str, Any]:
    """Return MCP-compatible error response."""
    return {"content": [{"type": "text", "text": f"Error: {text}"}], "isError": True}


# ---------------------------------------------------------------------------
# Tool 1: create_client_folder
# ---------------------------------------------------------------------------


@tool(
    "create_client_folder",
    "Create or get existing client folder structure in Google Drive",
    {"client_name": str},
)
async def create_client_folder(args: dict[str, Any]) -> dict[str, Any]:
    """Create the full client folder tree under the Drive root."""
    try:
        from proposal_assistant.config import get_config
        from proposal_assistant.drive.client import DriveClient
        from proposal_assistant.drive.folders import get_or_create_client_folder

        config = get_config()
        drive = DriveClient(config)
        folder_ids = get_or_create_client_folder(drive, args["client_name"])

        logger.info("Created client folder structure for %s", args["client_name"])
        return _ok(json.dumps(folder_ids))
    except Exception as e:
        logger.exception("DRIVE_PERMISSION: Failed to create client folder")
        return _err(f"DRIVE_PERMISSION: Unable to create client folder — {e}")


# ---------------------------------------------------------------------------
# Tool 2: create_deal_analysis
# ---------------------------------------------------------------------------


@tool(
    "create_deal_analysis",
    "Create a Deal Analysis Google Doc with structured content",
    {
        "client_name": str,
        "folder_id": str,
        "content": dict,
        "missing_info": list,
        "version": int,
    },
)
async def create_deal_analysis(args: dict[str, Any]) -> dict[str, Any]:
    """Create a versioned Deal Analysis document in Google Docs."""
    try:
        from proposal_assistant.config import get_config
        from proposal_assistant.docs.client import DocsClient
        from proposal_assistant.docs.deal_analysis import (
            create_versioned_document_title,
            populate_deal_analysis,
        )

        config = get_config()
        docs = DocsClient(config)

        title = create_versioned_document_title(
            f"{args['client_name']} - Deal Analysis",
            args["version"],
        )
        doc_id, doc_link = docs.create_document(title, args["folder_id"])
        populate_deal_analysis(docs, doc_id, args["content"], args.get("missing_info"))

        logger.info("Created Deal Analysis doc %s for %s", doc_id, args["client_name"])
        return _ok(json.dumps({"doc_id": doc_id, "doc_link": doc_link}))
    except Exception as e:
        logger.exception("DOCS_ERROR: Failed to create Deal Analysis")
        return _err(f"DOCS_ERROR: Failed to create the Deal Analysis document — {e}")


# ---------------------------------------------------------------------------
# Tool 3: create_proposal_deck
# ---------------------------------------------------------------------------


@tool(
    "create_proposal_deck",
    "Create a Proposal Deck by duplicating the template and populating slides",
    {"client_name": str, "folder_id": str, "content": dict},
)
async def create_proposal_deck(args: dict[str, Any]) -> dict[str, Any]:
    """Duplicate the Slides template and populate it with proposal content."""
    try:
        from proposal_assistant.config import get_config
        from proposal_assistant.slides.client import SlidesClient
        from proposal_assistant.slides.proposal_deck import populate_proposal_deck

        config = get_config()
        slides = SlidesClient(config)

        title = f"{args['client_name']} - Proposal"
        deck_id, deck_link = slides.duplicate_template(title, args["folder_id"])
        populate_proposal_deck(slides, deck_id, args["content"])

        logger.info("Created Proposal Deck %s for %s", deck_id, args["client_name"])
        return _ok(json.dumps({"deck_id": deck_id, "deck_link": deck_link}))
    except Exception as e:
        logger.exception("SLIDES_ERROR: Failed to create proposal deck")
        return _err(f"SLIDES_ERROR: Failed to create the proposal deck — {e}")


# ---------------------------------------------------------------------------
# Tool 4: share_document
# ---------------------------------------------------------------------------


@tool(
    "share_document",
    "Share a Google Drive file with a user by email",
    {"file_id": str, "email": str, "role": str},
)
async def share_document(args: dict[str, Any]) -> dict[str, Any]:
    """Share a Drive file (doc or deck) with the given email address."""
    try:
        from proposal_assistant.config import get_config
        from proposal_assistant.drive.client import DriveClient

        config = get_config()
        drive = DriveClient(config)

        role = args.get("role", "writer")
        drive.share_file(args["file_id"], args["email"], role)

        logger.info("Shared file %s with %s as %s", args["file_id"], args["email"], role)
        return _ok(f"Shared file {args['file_id']} with {args['email']} as {role}")
    except Exception as e:
        logger.exception("DRIVE_PERMISSION: Failed to share document")
        return _err(f"DRIVE_PERMISSION: Unable to share document — {e}")
