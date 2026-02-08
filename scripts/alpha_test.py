#!/usr/bin/env python3
"""Alpha test: End-to-end automated test for Proposal Assistant.

This script performs a real integration test of the full workflow:
1. Upload transcript to Slack
2. Wait for Deal Analysis document creation
3. Trigger approval (direct handler invocation)
4. Wait for Proposal deck creation

Requires:
- Bot to be running
- ALPHA_TEST_CHANNEL_ID env var set to a test channel
- All standard .env configuration
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from proposal_assistant.config import get_config
from proposal_assistant.slack.handlers import handle_approval

# Configuration
POLL_INTERVAL = 5  # seconds
MAX_WAIT_TIME = 180  # seconds (3 minutes)
TRANSCRIPT_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "transcripts" / "valid_transcript.md"

# URL patterns for link extraction
DOC_URL_PATTERN = re.compile(r"https://docs\.google\.com/document/d/[^\s<>|\]]+")
DECK_URL_PATTERN = re.compile(r"https://docs\.google\.com/presentation/d/[^\s<>|\]]+")


class AlphaTestResult:
    """Tracks test step results."""

    def __init__(self):
        self.steps: list[dict[str, Any]] = []

    def add_pass(self, name: str, detail: str | None = None) -> None:
        self.steps.append({"name": name, "passed": True, "detail": detail})

    def add_fail(self, name: str, error: str) -> None:
        self.steps.append({"name": name, "passed": False, "error": error})

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.steps if s["passed"])

    @property
    def total_count(self) -> int:
        return len(self.steps)

    @property
    def all_passed(self) -> bool:
        return all(s["passed"] for s in self.steps)


def upload_transcript(client: WebClient, channel_id: str) -> tuple[str | None, dict | None]:
    """Upload transcript file with 'Analyse' message.

    Returns:
        Tuple of (thread_ts, file_info) if successful, (None, None) on failure.
    """
    if not TRANSCRIPT_PATH.exists():
        print(f"Error: Transcript file not found at {TRANSCRIPT_PATH}")
        return None, None

    try:
        result = client.files_upload_v2(
            channel=channel_id,
            file=str(TRANSCRIPT_PATH),
            filename="alpha-test-client-discovery.md",
            initial_comment="Analyse",
        )

        response_data = result.data if hasattr(result, "data") else dict(result)
        uploaded_file_info = None

        # Method 1: files_upload_v2 returns {"ok": true, "files": [...]}
        files = response_data.get("files", [])
        if files:
            uploaded_file_info = files[0]
            shares = uploaded_file_info.get("shares", {})

            # Find thread_ts in public or private channel shares
            for share_type in ["public", "private"]:
                channel_shares = shares.get(share_type, {}).get(channel_id, [])
                if channel_shares:
                    return channel_shares[0].get("ts"), uploaded_file_info

        # Method 2: Look for file in result directly (older API format)
        file_info = response_data.get("file", {})
        if file_info:
            uploaded_file_info = file_info
            shares = file_info.get("shares", {})
            for share_type in ["public", "private"]:
                channel_shares = shares.get(share_type, {}).get(channel_id, [])
                if channel_shares:
                    return channel_shares[0].get("ts"), uploaded_file_info

        # Method 3: Fallback - search recent channel history for the file message
        print("  Shares not in response, searching channel history...")
        time.sleep(2)  # Give Slack time to index the message
        try:
            history = client.conversations_history(channel=channel_id, limit=10)
            for msg in history.get("messages", []):
                # Look for message with our file attachment
                msg_files = msg.get("files", [])
                for f in msg_files:
                    if f.get("name") == "alpha-test-client-discovery.md":
                        return msg.get("ts"), f
        except SlackApiError as e:
            print(f"  Could not search history: {e.response['error']}")

        # Debug output if all methods fail
        print(f"Warning: Could not extract thread_ts. Response keys: {list(response_data.keys())}")
        if files:
            print(f"  File info keys: {list(files[0].keys())}")
            print(f"  Shares: {files[0].get('shares', 'NOT PRESENT')}")
        return None, None

    except SlackApiError as e:
        print(f"Error uploading file: {e.response['error']}")
        return None, None


def poll_for_message(
    client: WebClient,
    channel_id: str,
    thread_ts: str,
    pattern: str,
    timeout: int = MAX_WAIT_TIME,
) -> dict[str, Any] | None:
    """Poll thread for a message containing the pattern.

    Returns:
        The matching message dict, or None if timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = client.conversations_replies(channel=channel_id, ts=thread_ts)
            messages = result.get("messages", [])

            for msg in messages:
                text = msg.get("text", "")
                if pattern in text:
                    return msg

        except SlackApiError as e:
            print(f"Error polling messages: {e.response['error']}")

        time.sleep(POLL_INTERVAL)

    return None


def extract_link(message: dict[str, Any], url_pattern: re.Pattern) -> str | None:
    """Extract a URL from message blocks or text."""
    # Check blocks first
    for block in message.get("blocks", []):
        if block.get("type") == "section":
            text = block.get("text", {}).get("text", "")
            match = url_pattern.search(text)
            if match:
                return match.group(0)

    # Fallback to plain text
    text = message.get("text", "")
    match = url_pattern.search(text)
    if match:
        return match.group(0)

    return None


def find_bot_message_ts(
    client: WebClient, channel_id: str, thread_ts: str, pattern: str
) -> str | None:
    """Find the timestamp of a bot message containing the pattern."""
    try:
        result = client.conversations_replies(channel=channel_id, ts=thread_ts)
        for msg in result.get("messages", []):
            if pattern in msg.get("text", ""):
                return msg.get("ts")
    except SlackApiError:
        pass
    return None


def create_say_function(client: WebClient, channel_id: str):
    """Create a say function that posts to the channel."""

    def say(text: str = "", blocks: list | None = None, thread_ts: str | None = None):
        try:
            client.chat_postMessage(
                channel=channel_id,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
        except SlackApiError as e:
            print(f"Error posting message: {e.response['error']}")

    return say


def run_alpha_test() -> AlphaTestResult:
    """Run the full alpha test workflow."""
    result = AlphaTestResult()

    # Load environment
    load_dotenv()
    config = get_config()

    channel_id = os.getenv("ALPHA_TEST_CHANNEL_ID")
    if not channel_id:
        result.add_fail("Configuration", "ALPHA_TEST_CHANNEL_ID not set")
        return result

    # Initialize Slack client
    client = WebClient(token=config.slack_bot_token)

    # Get bot user ID for filtering
    try:
        auth_result = client.auth_test()
        bot_user_id = auth_result.get("user_id")
    except SlackApiError as e:
        result.add_fail("Configuration", f"Failed to authenticate: {e.response['error']}")
        return result

    print(f"\nStarting alpha test in channel {channel_id}...\n")

    # Step 1: Upload transcript
    print("Step 1: Uploading transcript...")
    thread_ts = upload_transcript(client, channel_id)
    if thread_ts:
        result.add_pass("Upload transcript", f"thread_ts: {thread_ts}")
        print(f"  [PASS] Uploaded transcript (thread: {thread_ts})")
    else:
        result.add_fail("Upload transcript", "Failed to upload file")
        print("  [FAIL] Failed to upload transcript")
        return result

    # Step 2: Wait for Deal Analysis
    print("Step 2: Waiting for Deal Analysis...")
    deal_msg = poll_for_message(
        client, channel_id, thread_ts, "Deal Analysis created", timeout=MAX_WAIT_TIME
    )
    if deal_msg:
        doc_link = extract_link(deal_msg, DOC_URL_PATTERN)
        result.add_pass("Deal Analysis created", doc_link)
        print(f"  [PASS] Deal Analysis created")
        if doc_link:
            print(f"         Link: {doc_link}")
    else:
        result.add_fail("Deal Analysis created", f"Timed out after {MAX_WAIT_TIME}s")
        print(f"  [FAIL] Timed out waiting for Deal Analysis")
        return result

    # Step 3: Trigger approval
    print("Step 3: Triggering approval...")
    bot_message_ts = find_bot_message_ts(
        client, channel_id, thread_ts, "Deal Analysis created"
    )

    if not bot_message_ts:
        result.add_fail("Approval triggered", "Could not find bot message ts")
        print("  [FAIL] Could not find bot message timestamp")
        return result

    # Build approval payload (same structure as test_happy_path.py)
    approval_body = {
        "channel": {"id": channel_id},
        "message": {"thread_ts": thread_ts, "ts": bot_message_ts},
        "user": {"id": bot_user_id},  # Use bot user for testing
        "actions": [{"action_id": "approve_deck"}],
    }

    try:
        say_func = create_say_function(client, channel_id)
        handle_approval(approval_body, say_func, client)
        result.add_pass("Approval triggered")
        print("  [PASS] Approval triggered")
    except Exception as e:
        result.add_fail("Approval triggered", str(e))
        print(f"  [FAIL] Approval failed: {e}")
        return result

    # Step 4: Wait for Proposal Deck
    print("Step 4: Waiting for Proposal deck...")
    deck_msg = poll_for_message(
        client, channel_id, thread_ts, "Proposal deck created", timeout=MAX_WAIT_TIME
    )
    if deck_msg:
        deck_link = extract_link(deck_msg, DECK_URL_PATTERN)
        result.add_pass("Proposal deck created", deck_link)
        print(f"  [PASS] Proposal deck created")
        if deck_link:
            print(f"         Link: {deck_link}")
    else:
        result.add_fail("Proposal deck created", f"Timed out after {MAX_WAIT_TIME}s")
        print(f"  [FAIL] Timed out waiting for Proposal deck")

    return result


def print_report(result: AlphaTestResult, channel_id: str | None) -> None:
    """Print formatted test report."""
    print("\n" + "=" * 48)
    print("ALPHA TEST REPORT")
    print("=" * 48)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Channel: {channel_id or 'N/A'}")
    print()

    for step in result.steps:
        status = "[PASS]" if step["passed"] else "[FAIL]"
        print(f"{status} {step['name']}")
        if step.get("detail"):
            print(f"       Link: {step['detail']}")
        if step.get("error"):
            print(f"       Error: {step['error']}")

    print()
    print("-" * 48)
    status_text = "PASSED" if result.all_passed else "FAILED"
    print(f"RESULT: {result.passed_count}/{result.total_count} {status_text}")
    print("=" * 48)


def main() -> int:
    """Main entry point."""
    load_dotenv()
    channel_id = os.getenv("ALPHA_TEST_CHANNEL_ID")

    result = run_alpha_test()
    print_report(result, channel_id)

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
