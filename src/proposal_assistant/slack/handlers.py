"""Slack event handlers for Proposal Assistant."""

import logging
import urllib.request
from typing import Any

from slack_sdk import WebClient

from proposal_assistant.config import get_config
from proposal_assistant.docs.client import DocsClient
from proposal_assistant.docs.deal_analysis import populate_deal_analysis
from proposal_assistant.drive.client import DriveClient
from proposal_assistant.drive.folders import get_or_create_client_folder
from proposal_assistant.drive.permissions import share_with_channel_members
from proposal_assistant.llm.client import LLMClient, LLMError
from proposal_assistant.slack.messages import (
    format_analyzing,
    format_approval_buttons,
    format_deal_analysis_complete,
    format_deck_complete,
    format_error,
    format_generating_deck,
    format_rejection_confirmed,
)
from proposal_assistant.slides.client import SlidesClient
from proposal_assistant.slides.proposal_deck import populate_proposal_deck
from proposal_assistant.state.machine import StateMachine
from proposal_assistant.state.models import Event
from proposal_assistant.utils.parsing import extract_client_name
from proposal_assistant.utils.validation import validate_transcript

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
    user_id = message.get("user")
    files = message.get("files", [])

    logger.info(
        "Received Analyse command in channel=%s thread=%s",
        channel,
        thread_ts,
    )

    # 1. Check for file attachments
    if not files:
        error_msg = format_error("INPUT_MISSING")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 2. Filter for .md files only
    md_files = [f for f in files if f.get("name", "").lower().endswith(".md")]
    if not md_files:
        error_msg = format_error("INPUT_INVALID")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 3. Download and validate all .md files
    config = get_config()
    transcript_parts: list[str] = []
    file_ids: list[str] = []

    for file_info in md_files:
        file_name = file_info.get("name", "")
        download_url = file_info.get("url_private_download")

        if not download_url:
            error_msg = format_error("INPUT_INVALID")
            say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
            return

        try:
            req = urllib.request.Request(
                download_url,
                headers={"Authorization": f"Bearer {config.slack_bot_token}"},
            )
            with urllib.request.urlopen(req) as response:
                content = response.read().decode("utf-8")
        except Exception as e:
            logger.error("Failed to download file %s: %s", file_name, e)
            error_msg = format_error("INPUT_INVALID")
            say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
            return

        # Validate each transcript
        validation = validate_transcript(file_name, content)
        if not validation.is_valid:
            error_msg = format_error("INPUT_INVALID")
            say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
            return

        transcript_parts.append(content)
        file_ids.append(file_info.get("id"))

    # Use first file for client name extraction
    first_file_name = md_files[0].get("name", "")

    # 5. Transition state to GENERATING_DEAL_ANALYSIS
    state_machine = StateMachine()
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        user_id=user_id,
        event=Event.ANALYSE_REQUESTED,
        input_transcript_file_ids=file_ids,
    )

    # Acknowledge with "Analyzing..." message
    analyzing_msg = format_analyzing()
    say(text=analyzing_msg["text"], blocks=analyzing_msg["blocks"], thread_ts=thread_ts)

    # 6. Extract client name and create folder structure
    client_name = extract_client_name(first_file_name) or "unknown-client"

    try:
        drive = DriveClient(config)
        folders = get_or_create_client_folder(drive, client_name)
    except Exception as e:
        logger.error("Failed to create client folder: %s", e)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type="DRIVE_PERMISSION",
            error_message=str(e),
        )
        error_msg = format_error("DRIVE_PERMISSION")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 6. Build context and call LLM
    try:
        llm = LLMClient(config)
        result = llm.generate_deal_analysis(transcript=transcript_parts)
        deal_analysis_content = result["content"]
        missing_info = result.get("missing_info", [])
    except LLMError as e:
        logger.error("LLM error: %s (type=%s)", e, e.error_type)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type=e.error_type,
            error_message=str(e),
        )
        error_msg = format_error(e.error_type)
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return
    except Exception as e:
        logger.error("Unexpected LLM error: %s", e)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type="LLM_ERROR",
            error_message=str(e),
        )
        error_msg = format_error("LLM_ERROR")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 7. Create Google Doc
    try:
        docs = DocsClient(config)
        doc_title = f"{client_name} - Deal Analysis"
        doc_id, doc_link = docs.create_document(
            doc_title, folders["analyse_folder_id"]
        )
        populate_deal_analysis(docs, doc_id, deal_analysis_content, missing_info)
    except Exception as e:
        logger.error("Failed to create Deal Analysis doc: %s", e)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type="DOCS_ERROR",
            error_message=str(e),
        )
        error_msg = format_error("DOCS_ERROR")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 8. Share doc with channel members
    try:
        shared_emails = share_with_channel_members(drive, doc_id, channel, client)
        logger.info("Shared Deal Analysis doc with %d users", len(shared_emails))
    except Exception as e:
        logger.warning("Failed to share Deal Analysis doc: %s", e)

    # 9. Transition to WAITING_FOR_APPROVAL
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.DEAL_ANALYSIS_CREATED,
        client_name=client_name,
        client_folder_id=folders["client_folder_id"],
        analyse_folder_id=folders["analyse_folder_id"],
        proposals_folder_id=folders["proposals_folder_id"],
        deal_analysis_doc_id=doc_id,
        deal_analysis_link=doc_link,
        deal_analysis_content=deal_analysis_content,
        missing_info_items=missing_info,
    )

    # 10. Send message with link + approval buttons
    completion_msg = format_deal_analysis_complete(doc_link, missing_info)
    approval_buttons = format_approval_buttons()

    blocks = completion_msg["blocks"] + [approval_buttons]
    say(text=completion_msg["text"], blocks=blocks, thread_ts=thread_ts)

    logger.info(
        "Deal Analysis complete for %s, doc_id=%s, awaiting approval",
        client_name,
        doc_id,
    )


def handle_approval(
    body: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle the approval button click to create proposal deck.

    Args:
        body: Slack action payload containing channel, thread, and user info.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    channel = body.get("channel", {}).get("id")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id")

    logger.info(
        "Received approval in channel=%s thread=%s from user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # 1. Get thread state
    state_machine = StateMachine()
    thread_state = state_machine.get_state(thread_ts, channel, user_id)

    # Check for missing state
    if not thread_state.deal_analysis_content or not thread_state.proposals_folder_id:
        logger.error("Missing state data for approval: content=%s, folder=%s",
                     bool(thread_state.deal_analysis_content),
                     bool(thread_state.proposals_folder_id))
        error_msg = format_error("STATE_MISSING")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 2. Transition to GENERATING_DECK
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.APPROVED,
    )

    # Acknowledge with "Generating..." message
    generating_msg = format_generating_deck()
    say(text=generating_msg["text"], blocks=generating_msg["blocks"], thread_ts=thread_ts)

    config = get_config()

    # 3. Generate proposal deck content via LLM
    try:
        llm = LLMClient(config)
        result = llm.generate_proposal_deck_content(thread_state.deal_analysis_content)
        deck_content = result["content"]
    except LLMError as e:
        logger.error("LLM error generating deck: %s (type=%s)", e, e.error_type)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type=e.error_type,
            error_message=str(e),
        )
        error_msg = format_error(e.error_type)
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return
    except Exception as e:
        logger.error("Unexpected LLM error: %s", e)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type="LLM_ERROR",
            error_message=str(e),
        )
        error_msg = format_error("LLM_ERROR")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 4. Create Google Slides presentation
    try:
        slides = SlidesClient(config)
        deck_title = f"{thread_state.client_name} - Proposal"
        deck_id, deck_link = slides.duplicate_template(
            deck_title, thread_state.proposals_folder_id
        )
        populate_proposal_deck(slides, deck_id, deck_content)
    except Exception as e:
        logger.error("Failed to create proposal deck: %s", e)
        state_machine.transition(
            thread_ts=thread_ts,
            channel_id=channel,
            event=Event.FAILED,
            error_type="SLIDES_ERROR",
            error_message=str(e),
        )
        error_msg = format_error("SLIDES_ERROR")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 5. Share deck with channel members
    try:
        drive = DriveClient(config)
        shared_emails = share_with_channel_members(drive, deck_id, channel, client)
        logger.info("Shared proposal deck with %d users", len(shared_emails))
    except Exception as e:
        logger.warning("Failed to share proposal deck: %s", e)

    # 6. Transition to DONE
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.DECK_CREATED,
        slides_deck_id=deck_id,
        slides_deck_link=deck_link,
    )

    # 7. Send completion message with link
    completion_msg = format_deck_complete(deck_link)
    say(text=completion_msg["text"], blocks=completion_msg["blocks"], thread_ts=thread_ts)

    logger.info(
        "Proposal deck complete for %s, deck_id=%s",
        thread_state.client_name,
        deck_id,
    )


def handle_rejection(
    body: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle the rejection button click.

    Args:
        body: Slack action payload containing channel, thread, and user info.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    channel = body.get("channel", {}).get("id")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id")

    logger.info(
        "Received rejection in channel=%s thread=%s from user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # 1. Transition to DONE
    state_machine = StateMachine()
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.REJECTED,
    )

    # 2. Send confirmation message
    confirmation_msg = format_rejection_confirmed()
    say(text=confirmation_msg["text"], blocks=confirmation_msg["blocks"], thread_ts=thread_ts)

    logger.info("Proposal deck rejected for thread=%s", thread_ts)
