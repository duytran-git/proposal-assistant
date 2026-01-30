"""Slack event handlers for Proposal Assistant."""

import logging
import re
import urllib.request
from typing import Any

from slack_sdk import WebClient

from proposal_assistant.config import get_config
from proposal_assistant.docs.client import DocsClient
from proposal_assistant.docs.deal_analysis import (
    create_versioned_document_title,
    populate_deal_analysis,
)
from proposal_assistant.drive.client import DriveClient
from proposal_assistant.drive.folders import get_or_create_client_folder
from proposal_assistant.drive.permissions import (
    share_with_channel_members,
    share_with_user_by_id,
)
from proposal_assistant.llm.client import LLMClient, LLMError
from proposal_assistant.slack.messages import (
    format_analyzing,
    format_approval_buttons,
    format_cloud_consent,
    format_deal_analysis_complete,
    format_deck_complete,
    format_error,
    format_fetch_failures,
    format_generating_deck,
    format_regenerating,
    format_rejection_confirmed,
)
from proposal_assistant.slides.client import SlidesClient
from proposal_assistant.slides.proposal_deck import populate_proposal_deck
from proposal_assistant.state.machine import StateMachine
from proposal_assistant.state.models import Event, State
from proposal_assistant.utils.parsing import extract_client_name
from proposal_assistant.utils.validation import validate_transcript
from proposal_assistant.web.fetcher import WebFetcher

logger = logging.getLogger(__name__)

# URL regex pattern for extracting URLs from message text
URL_PATTERN = re.compile(
    r"https?://[^\s<>\[\]()\"'`]+",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    """Extract URLs from message text.

    Args:
        text: Message text that may contain URLs.

    Returns:
        List of unique URLs found in the text.
    """
    if not text:
        return []
    urls = URL_PATTERN.findall(text)
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


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
    thread_ts: str | None = message.get("thread_ts") or message.get("ts")
    channel: str | None = message.get("channel")
    channel_type: str | None = message.get("channel_type")
    user_id: str | None = message.get("user")
    files = message.get("files", [])

    logger.info(
        "Received Analyse command in channel=%s thread=%s channel_type=%s",
        channel,
        thread_ts,
        channel_type,
    )

    # 1. Check for file attachments
    if not files:
        error_msg = format_error("INPUT_MISSING")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # Validate required fields
    if not channel or not thread_ts or not user_id:
        logger.error("Missing required message fields")
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

    # 4. Transition state to GENERATING_DEAL_ANALYSIS
    state_machine = StateMachine()
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        channel_type=channel_type,
        user_id=user_id,
        event=Event.ANALYSE_REQUESTED,
        input_transcript_file_ids=file_ids,
        input_transcript_content=transcript_parts,
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

    # 6. Extract URLs from message text and fetch web content
    message_text = message.get("text", "")
    urls = extract_urls(message_text)
    web_content: list[str] | None = None

    if urls:
        logger.info("Found %d URLs in message, fetching web content", len(urls))
        fetcher = WebFetcher()
        results = fetcher.fetch_multiple(urls)
        # Separate successful and failed fetches
        web_content = [content for _, content in results if content is not None]
        failed_urls = [url for url, content in results if content is None]

        if failed_urls:
            logger.warning("Failed to fetch %d URLs: %s", len(failed_urls), failed_urls)
            failure_msg = format_fetch_failures(failed_urls)
            say(
                text=failure_msg["text"],
                blocks=failure_msg["blocks"],
                thread_ts=thread_ts,
            )

        if web_content:
            logger.info("Fetched %d/%d URLs successfully", len(web_content), len(urls))
        else:
            web_content = None

    # 7. Build context and call LLM
    llm = LLMClient(config)
    try:
        result = llm.generate_deal_analysis(
            transcript=transcript_parts,
            web_content=web_content,
        )
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
        # Show cloud consent buttons if LLM is offline and cloud is available
        if e.error_type == "LLM_OFFLINE" and llm.cloud_available:
            consent_msg = format_cloud_consent()
            say(
                text=consent_msg["text"],
                blocks=consent_msg["blocks"],
                thread_ts=thread_ts,
            )
        else:
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

    # 8. Create Google Doc
    try:
        docs = DocsClient(config)
        doc_title = f"{client_name} - Deal Analysis"
        doc_id, doc_link = docs.create_document(doc_title, folders["analyse_folder_id"])
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

    # 9. Share doc with user (DM) or channel members
    try:
        if channel_type == "im":
            email = share_with_user_by_id(drive, doc_id, user_id, client)
            if email:
                logger.info("Shared Deal Analysis doc with user %s", email)
        else:
            shared_emails = share_with_channel_members(drive, doc_id, channel, client)
            logger.info("Shared Deal Analysis doc with %d users", len(shared_emails))
    except Exception as e:
        logger.warning("Failed to share Deal Analysis doc: %s", e)

    # 10. Transition to WAITING_FOR_APPROVAL
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

    # 11. Send message with link + approval buttons
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
    channel: str | None = body.get("channel", {}).get("id")
    thread_ts: str | None = body.get("message", {}).get("thread_ts") or body.get(
        "message", {}
    ).get("ts")
    user_id: str | None = body.get("user", {}).get("id")

    logger.info(
        "Received approval in channel=%s thread=%s from user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # Validate required fields
    if not channel or not thread_ts or not user_id:
        logger.error("Missing required action payload fields")
        return

    # 1. Get thread state
    state_machine = StateMachine()
    thread_state = state_machine.get_state(thread_ts, channel, user_id)

    # Check for missing state
    if not thread_state.deal_analysis_content or not thread_state.proposals_folder_id:
        logger.error(
            "Missing state data for approval: content=%s, folder=%s",
            bool(thread_state.deal_analysis_content),
            bool(thread_state.proposals_folder_id),
        )
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
    say(
        text=generating_msg["text"],
        blocks=generating_msg["blocks"],
        thread_ts=thread_ts,
    )

    config = get_config()

    # 3. Prepare deal analysis content
    # If user uploaded a doc, parse it into structured format
    deal_analysis = thread_state.deal_analysis_content
    if deal_analysis.get("source") == "user_uploaded":
        from proposal_assistant.utils.doc_parser import parse_deal_analysis

        raw_content = deal_analysis.get("raw_content", "")
        deal_analysis = parse_deal_analysis(raw_content)
        logger.info("Using parsed user-uploaded deal analysis")

    # 4. Generate proposal deck content via LLM
    try:
        llm = LLMClient(config)
        result = llm.generate_proposal_deck_content(deal_analysis)
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
        assert thread_state.proposals_folder_id is not None  # Checked above
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

    # 5. Share deck with user (DM) or channel members
    try:
        drive = DriveClient(config)
        if thread_state.channel_type == "im":
            email = share_with_user_by_id(drive, deck_id, user_id, client)
            if email:
                logger.info("Shared proposal deck with user %s", email)
        else:
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
    say(
        text=completion_msg["text"],
        blocks=completion_msg["blocks"],
        thread_ts=thread_ts,
    )

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
    channel: str | None = body.get("channel", {}).get("id")
    thread_ts: str | None = body.get("message", {}).get("thread_ts") or body.get(
        "message", {}
    ).get("ts")
    user_id: str | None = body.get("user", {}).get("id")

    logger.info(
        "Received rejection in channel=%s thread=%s from user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # Validate required fields
    if not channel or not thread_ts:
        logger.error("Missing required action payload fields")
        return

    # 1. Transition to DONE
    state_machine = StateMachine()
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.REJECTED,
    )

    # 2. Send confirmation message
    confirmation_msg = format_rejection_confirmed()
    say(
        text=confirmation_msg["text"],
        blocks=confirmation_msg["blocks"],
        thread_ts=thread_ts,
    )

    logger.info("Proposal deck rejected for thread=%s", thread_ts)


def handle_regenerate(
    body: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle the regenerate button click to create a new Deal Analysis version.

    Args:
        body: Slack action payload containing channel, thread, and user info.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    channel: str | None = body.get("channel", {}).get("id")
    thread_ts: str | None = body.get("message", {}).get("thread_ts") or body.get(
        "message", {}
    ).get("ts")
    user_id: str | None = body.get("user", {}).get("id")

    logger.info(
        "Received regenerate request in channel=%s thread=%s from user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # Validate required fields
    if not channel or not thread_ts or not user_id:
        logger.error("Missing required action payload fields")
        return

    # 1. Get thread state
    state_machine = StateMachine()
    thread_state = state_machine.get_state(thread_ts, channel, user_id)

    # Check for missing state
    if not thread_state.input_transcript_content or not thread_state.analyse_folder_id:
        logger.error(
            "Missing state data for regenerate: transcripts=%s, folder=%s",
            bool(thread_state.input_transcript_content),
            bool(thread_state.analyse_folder_id),
        )
        error_msg = format_error("STATE_MISSING")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 2. Calculate new version and transition to GENERATING_DEAL_ANALYSIS
    new_version = thread_state.deal_analysis_version + 1
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.REGENERATE_REQUESTED,
        deal_analysis_version=new_version,
    )

    # Acknowledge with "Regenerating..." message
    regenerating_msg = format_regenerating(new_version)
    say(
        text=regenerating_msg["text"],
        blocks=regenerating_msg["blocks"],
        thread_ts=thread_ts,
    )

    config = get_config()

    # 3. Re-run LLM with stored transcript content
    try:
        llm = LLMClient(config)
        result = llm.generate_deal_analysis(
            transcript=thread_state.input_transcript_content
        )
        deal_analysis_content = result["content"]
        missing_info = result.get("missing_info", [])
    except LLMError as e:
        logger.error("LLM error during regenerate: %s (type=%s)", e, e.error_type)
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
        logger.error("Unexpected LLM error during regenerate: %s", e)
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

    # 4. Create new Google Doc with version number
    try:
        docs = DocsClient(config)
        base_title = f"{thread_state.client_name} - Deal Analysis"
        doc_title = create_versioned_document_title(base_title, new_version)
        assert thread_state.analyse_folder_id is not None  # Checked above
        doc_id, doc_link = docs.create_document(
            doc_title, thread_state.analyse_folder_id
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

    # 5. Share doc with user (DM) or channel members
    try:
        drive = DriveClient(config)
        if thread_state.channel_type == "im":
            email = share_with_user_by_id(drive, doc_id, user_id, client)
            if email:
                logger.info(
                    "Shared Deal Analysis v%d doc with user %s", new_version, email
                )
        else:
            shared_emails = share_with_channel_members(drive, doc_id, channel, client)
            logger.info(
                "Shared Deal Analysis v%d doc with %d users",
                new_version,
                len(shared_emails),
            )
    except Exception as e:
        logger.warning("Failed to share Deal Analysis doc: %s", e)

    # 6. Transition to WAITING_FOR_APPROVAL
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.DEAL_ANALYSIS_CREATED,
        deal_analysis_doc_id=doc_id,
        deal_analysis_link=doc_link,
        deal_analysis_content=deal_analysis_content,
        missing_info_items=missing_info,
    )

    # 7. Send message with link + approval buttons
    completion_msg = format_deal_analysis_complete(doc_link, missing_info)
    approval_buttons = format_approval_buttons()

    blocks = completion_msg["blocks"] + [approval_buttons]
    say(text=completion_msg["text"], blocks=blocks, thread_ts=thread_ts)

    logger.info(
        "Deal Analysis v%d complete for %s, doc_id=%s, awaiting approval",
        new_version,
        thread_state.client_name,
        doc_id,
    )


def handle_updated_deal_analysis(
    message: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle file upload in WAITING_FOR_APPROVAL state.

    Detects .docx or .md file uploads and triggers deck generation
    using the uploaded content as the deal analysis.

    Args:
        message: Slack message event payload.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    thread_ts: str | None = message.get("thread_ts") or message.get("ts")
    channel: str | None = message.get("channel")
    user_id: str | None = message.get("user")
    files = message.get("files", [])

    # Must have files and be in a thread
    if not files or not thread_ts:
        return

    # Validate required fields
    if not channel or not user_id:
        logger.error("Missing required message fields")
        return

    logger.info(
        "Checking for updated deal analysis in channel=%s thread=%s",
        channel,
        thread_ts,
    )

    # 1. Get thread state to check current state
    state_machine = StateMachine()
    try:
        thread_state = state_machine.get_state(thread_ts, channel, user_id)
    except Exception:
        # No existing state for this thread, ignore
        return

    # 2. Only proceed if in WAITING_FOR_APPROVAL state
    if thread_state.state != State.WAITING_FOR_APPROVAL:
        logger.debug(
            "Thread not in WAITING_FOR_APPROVAL (state=%s), ignoring file upload",
            thread_state.state,
        )
        return

    # 3. Filter for .docx or .md files
    valid_files = [
        f for f in files if f.get("name", "").lower().endswith((".docx", ".md"))
    ]

    if not valid_files:
        logger.debug("No .docx or .md files found in upload")
        return

    # 4. Download the first valid file
    file_info = valid_files[0]
    file_name = file_info.get("name", "")
    download_url = file_info.get("url_private_download")

    if not download_url:
        logger.error("No download URL for file %s", file_name)
        return

    config = get_config()

    try:
        req = urllib.request.Request(
            download_url,
            headers={"Authorization": f"Bearer {config.slack_bot_token}"},
        )
        with urllib.request.urlopen(req) as response:
            raw_content = response.read()
    except Exception as e:
        logger.error("Failed to download file %s: %s", file_name, e)
        error_msg = format_error("INPUT_INVALID")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 5. Parse file into structured deal analysis format
    from proposal_assistant.utils.doc_parser import parse_deal_analysis

    try:
        deal_analysis_content = parse_deal_analysis(raw_content, filename=file_name)
    except Exception as e:
        logger.error("Failed to parse file %s: %s", file_name, e)
        error_msg = format_error("INPUT_INVALID")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # 6. Transition to GENERATING_DECK with UPDATED_DEAL_ANALYSIS_PROVIDED
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.UPDATED_DEAL_ANALYSIS_PROVIDED,
        deal_analysis_content=deal_analysis_content,
    )

    # 7. Acknowledge with generating message
    generating_msg = format_generating_deck()
    say(
        text=generating_msg["text"],
        blocks=generating_msg["blocks"],
        thread_ts=thread_ts,
    )

    # 8. Generate proposal deck content via LLM
    try:
        llm = LLMClient(config)
        result = llm.generate_proposal_deck_content(deal_analysis_content)
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

    # 9. Create Google Slides presentation
    try:
        slides = SlidesClient(config)
        deck_title = f"{thread_state.client_name} - Proposal"
        if not thread_state.proposals_folder_id:
            raise ValueError("Missing proposals folder ID")
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

    # 10. Share deck with user (DM) or channel members
    try:
        drive = DriveClient(config)
        if thread_state.channel_type == "im":
            email = share_with_user_by_id(drive, deck_id, user_id, client)
            if email:
                logger.info("Shared proposal deck with user %s", email)
        else:
            shared_emails = share_with_channel_members(drive, deck_id, channel, client)
            logger.info("Shared proposal deck with %d users", len(shared_emails))
    except Exception as e:
        logger.warning("Failed to share proposal deck: %s", e)

    # 11. Transition to DONE
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.DECK_CREATED,
        slides_deck_id=deck_id,
        slides_deck_link=deck_link,
    )

    # 12. Send completion message with link
    completion_msg = format_deck_complete(deck_link)
    say(
        text=completion_msg["text"],
        blocks=completion_msg["blocks"],
        thread_ts=thread_ts,
    )

    logger.info(
        "Proposal deck created from updated Deal Analysis for %s, deck_id=%s",
        thread_state.client_name,
        deck_id,
    )


def handle_cloud_consent_yes(
    body: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle user accepting cloud AI usage.

    Retries the analysis using cloud AI instead of local Ollama.

    Args:
        body: Slack action payload containing channel, thread, and user info.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    channel: str | None = body.get("channel", {}).get("id")
    thread_ts: str | None = body.get("message", {}).get("thread_ts") or body.get(
        "message", {}
    ).get("ts")
    user_id: str | None = body.get("user", {}).get("id")

    logger.info(
        "User accepted cloud AI in channel=%s thread=%s user=%s",
        channel,
        thread_ts,
        user_id,
    )

    # Validate required fields
    if not channel or not thread_ts or not user_id:
        logger.error("Missing required action payload fields")
        return

    # Get thread state to retrieve stored transcript
    state_machine = StateMachine()
    thread_state = state_machine.get_state(thread_ts, channel, user_id)

    # Check for required state data
    if not thread_state.input_transcript_content:
        logger.error("Missing transcript content for cloud retry")
        error_msg = format_error("STATE_MISSING")
        say(text=error_msg["text"], blocks=error_msg["blocks"], thread_ts=thread_ts)
        return

    # Transition to GENERATING_DEAL_ANALYSIS with cloud consent
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.CLOUD_CONSENT_GIVEN,
        cloud_consent_given=True,
    )

    # Acknowledge with analyzing message
    analyzing_msg = format_analyzing()
    say(text=analyzing_msg["text"], blocks=analyzing_msg["blocks"], thread_ts=thread_ts)

    config = get_config()

    # Retry LLM call with cloud
    try:
        llm = LLMClient(config)
        result = llm.generate_deal_analysis(
            transcript=thread_state.input_transcript_content,
            use_cloud=True,
        )
        deal_analysis_content = result["content"]
        missing_info = result.get("missing_info", [])
    except LLMError as e:
        logger.error("Cloud LLM error: %s (type=%s)", e, e.error_type)
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
        logger.error("Unexpected cloud LLM error: %s", e)
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

    # Create Google Doc
    try:
        drive = DriveClient(config)
        docs = DocsClient(config)
        doc_title = f"{thread_state.client_name} - Deal Analysis"
        if not thread_state.analyse_folder_id:
            raise ValueError("Missing analyse folder ID")
        doc_id, doc_link = docs.create_document(
            doc_title, thread_state.analyse_folder_id
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

    # Share doc with user (DM) or channel members
    try:
        if thread_state.channel_type == "im":
            email = share_with_user_by_id(drive, doc_id, user_id, client)
            if email:
                logger.info("Shared Deal Analysis doc with user %s", email)
        else:
            shared_emails = share_with_channel_members(drive, doc_id, channel, client)
            logger.info("Shared Deal Analysis doc with %d users", len(shared_emails))
    except Exception as e:
        logger.warning("Failed to share Deal Analysis doc: %s", e)

    # Transition to WAITING_FOR_APPROVAL
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.DEAL_ANALYSIS_CREATED,
        deal_analysis_doc_id=doc_id,
        deal_analysis_link=doc_link,
        deal_analysis_content=deal_analysis_content,
        missing_info_items=missing_info,
    )

    # Send message with link + approval buttons
    completion_msg = format_deal_analysis_complete(doc_link, missing_info)
    approval_buttons = format_approval_buttons()

    blocks = completion_msg["blocks"] + [approval_buttons]
    say(text=completion_msg["text"], blocks=blocks, thread_ts=thread_ts)

    logger.info(
        "Deal Analysis complete via cloud for %s, doc_id=%s, awaiting approval",
        thread_state.client_name,
        doc_id,
    )


def handle_cloud_consent_no(
    body: dict[str, Any],
    say: Any,
    client: WebClient,
) -> None:
    """Handle user declining cloud AI usage.

    Cancels the operation with a message.

    Args:
        body: Slack action payload containing channel, thread, and user info.
        say: Slack say function for replying in thread.
        client: Slack WebClient for API calls.
    """
    channel: str | None = body.get("channel", {}).get("id")
    thread_ts: str | None = body.get("message", {}).get("thread_ts") or body.get(
        "message", {}
    ).get("ts")

    logger.info(
        "User declined cloud AI in channel=%s thread=%s",
        channel,
        thread_ts,
    )

    # Validate required fields
    if not channel or not thread_ts:
        logger.error("Missing required action payload fields")
        return

    # Transition to failed/cancelled state
    state_machine = StateMachine()
    state_machine.transition(
        thread_ts=thread_ts,
        channel_id=channel,
        event=Event.REJECTED,
    )

    say(text=":ok_hand: Got it, analysis cancelled.", thread_ts=thread_ts)
