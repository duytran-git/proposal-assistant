"""End-to-end tests for the full happy path flow.

Tests the complete workflow: Attach transcript -> Analyse -> Yes -> Both docs created.
All external APIs (Slack, Google Drive, Google Docs, Google Slides, LLM) are mocked.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.slack.handlers import handle_analyse_command, handle_approval
from proposal_assistant.state.models import Event, State, ThreadState

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def transcript_content():
    """Load valid transcript fixture."""
    transcript_path = FIXTURES_DIR / "transcripts" / "valid_transcript.md"
    return transcript_path.read_text()


@pytest.fixture
def deal_analysis_response():
    """Load deal analysis LLM response fixture."""
    response_path = FIXTURES_DIR / "llm_responses" / "deal_analysis_response.json"
    return json.loads(response_path.read_text())


@pytest.fixture
def proposal_deck_response():
    """Load proposal deck LLM response fixture."""
    response_path = FIXTURES_DIR / "llm_responses" / "proposal_deck_response.json"
    return json.loads(response_path.read_text())


@pytest.fixture
def mock_config():
    """Create a mock Config object with all required fields."""
    config = MagicMock()
    config.slack_bot_token = "xoxb-test-token"
    config.google_service_account_json = '{"type": "service_account"}'
    config.google_drive_root_folder_id = "root_folder_123"
    config.google_slides_template_id = "template_123"
    config.ollama_base_url = "http://localhost:11434"
    config.ollama_model = "llama3.2"
    return config


@pytest.fixture
def slack_message_with_file():
    """Create a Slack message payload with file attachment."""
    return {
        "ts": "1706500000.000001",
        "channel": "C_TEST_CHANNEL",
        "user": "U_TEST_USER",
        "text": "Analyse",
        "files": [
            {
                "id": "F_TEST_FILE",
                "name": "acme-corp-discovery-call.md",
                "url_private_download": "https://files.slack.com/files/T123/F123/transcript.md",
                "mimetype": "text/markdown",
            }
        ],
    }


@pytest.fixture
def approval_action_body():
    """Create a Slack action payload for approval button click."""
    return {
        "channel": {"id": "C_TEST_CHANNEL"},
        "message": {"thread_ts": "1706500000.000001", "ts": "1706500000.000002"},
        "user": {"id": "U_TEST_USER"},
        "actions": [{"action_id": "approve_deck"}],
    }


@pytest.fixture
def mock_say():
    """Create a mock say function that tracks calls."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock Slack WebClient."""
    return MagicMock()


class TestHappyPath:
    """End-to-end test for the complete happy path flow."""

    def test_full_happy_path_creates_both_documents(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        approval_action_body,
        mock_config,
        transcript_content,
        deal_analysis_response,
        proposal_deck_response,
    ):
        """Full flow: Analyse -> Deal Analysis -> Approve -> Proposal Deck."""
        state_transitions = []
        thread_state_data = {}

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch("proposal_assistant.slack.handlers.validate_transcript") as validate,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.extract_client_name") as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch(
                "proposal_assistant.slack.handlers.populate_deal_analysis"
            ) as populate_deal,
            patch(
                "proposal_assistant.slack.handlers.populate_proposal_deck"
            ) as populate_deck,
            patch(
                "proposal_assistant.slack.handlers.share_with_channel_members"
            ) as share,
        ):
            # Configure get_config
            get_config.return_value = mock_config

            # Mock Slack file download
            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            # Mock validation (success)
            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)

            # Track state transitions
            mock_state_machine = MagicMock()

            def track_transition(**kwargs):
                state_transitions.append(kwargs)
                # Capture state data for approval flow
                if kwargs.get("event") == Event.DEAL_ANALYSIS_CREATED:
                    thread_state_data.update(kwargs)

            mock_state_machine.transition.side_effect = track_transition

            # Mock get_state for approval flow - return ThreadState with captured data
            def get_state(thread_ts, channel, user_id):
                return ThreadState(
                    thread_ts=thread_ts,
                    channel_id=channel,
                    user_id=user_id,
                    client_name=thread_state_data.get("client_name", "acme-corp"),
                    proposals_folder_id=thread_state_data.get(
                        "proposals_folder_id", "folder_proposals_123"
                    ),
                    deal_analysis_content=thread_state_data.get(
                        "deal_analysis_content"
                    ),
                    deal_analysis_doc_id=thread_state_data.get("deal_analysis_doc_id"),
                    deal_analysis_link=thread_state_data.get("deal_analysis_link"),
                    state=State.WAITING_FOR_APPROVAL,
                )

            mock_state_machine.get_state.side_effect = get_state
            StateMachine.return_value = mock_state_machine

            # Mock client name extraction
            extract.return_value = "acme-corp"

            # Mock Drive folder creation
            get_folders.return_value = {
                "client_folder_id": "folder_client_123",
                "meetings_folder_id": "folder_meetings_123",
                "analyse_folder_id": "folder_analyse_123",
                "proposals_folder_id": "folder_proposals_123",
                "references_folder_id": "folder_references_123",
            }

            # Mock LLM responses (both deal analysis and proposal deck)
            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": deal_analysis_response["deal_analysis"],
                "missing_info": deal_analysis_response["missing_info"],
                "raw_response": json.dumps(deal_analysis_response),
            }
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": proposal_deck_response["content"],
                "raw_response": json.dumps(proposal_deck_response),
            }
            LLMClient.return_value = mock_llm

            # Mock Docs creation
            mock_docs = MagicMock()
            doc_id = "doc_deal_analysis_123"
            doc_link = f"https://docs.google.com/document/d/{doc_id}"
            mock_docs.create_document.return_value = (doc_id, doc_link)
            DocsClient.return_value = mock_docs

            # Mock Slides creation
            mock_slides = MagicMock()
            deck_id = "deck_proposal_123"
            deck_link = f"https://docs.google.com/presentation/d/{deck_id}"
            mock_slides.duplicate_template.return_value = (deck_id, deck_link)
            SlidesClient.return_value = mock_slides

            # Mock sharing
            share.return_value = ["user1@example.com", "user2@example.com"]

            # ─────────────────────────────────────────────────────────────────
            # PHASE 1: Execute Analyse command
            # ─────────────────────────────────────────────────────────────────
            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify Phase 1 state transitions (2 transitions)
            assert (
                len(state_transitions) == 2
            ), f"Expected 2 transitions after Analyse, got {len(state_transitions)}"

            # First transition: ANALYSE_REQUESTED
            assert state_transitions[0]["event"] == Event.ANALYSE_REQUESTED
            assert state_transitions[0]["thread_ts"] == "1706500000.000001"

            # Second transition: DEAL_ANALYSIS_CREATED
            assert state_transitions[1]["event"] == Event.DEAL_ANALYSIS_CREATED
            assert state_transitions[1]["deal_analysis_doc_id"] == doc_id
            assert state_transitions[1]["deal_analysis_link"] == doc_link
            assert (
                state_transitions[1]["deal_analysis_content"]
                == deal_analysis_response["deal_analysis"]
            )

            # Verify Phase 1 messages (2 messages)
            assert mock_say.call_count == 2
            assert mock_say.call_args_list[0][1]["text"] == "Analyzing transcript..."
            assert mock_say.call_args_list[1][1]["text"] == "Deal Analysis created"

            # Verify approval buttons are present
            blocks = mock_say.call_args_list[1][1]["blocks"]
            actions_block = next(
                (b for b in blocks if b.get("type") == "actions"), None
            )
            assert actions_block is not None, "Approval buttons not found"

            # ─────────────────────────────────────────────────────────────────
            # PHASE 2: Execute Approval
            # ─────────────────────────────────────────────────────────────────
            handle_approval(approval_action_body, mock_say, mock_client)

            # Verify Phase 2 state transitions (2 more transitions = 4 total)
            assert (
                len(state_transitions) == 4
            ), f"Expected 4 total transitions, got {len(state_transitions)}"

            # Third transition: APPROVED
            assert state_transitions[2]["event"] == Event.APPROVED

            # Fourth transition: DECK_CREATED
            assert state_transitions[3]["event"] == Event.DECK_CREATED
            assert state_transitions[3]["slides_deck_id"] == deck_id
            assert state_transitions[3]["slides_deck_link"] == deck_link

            # Verify Phase 2 messages (2 more = 4 total)
            assert mock_say.call_count == 4
            assert (
                mock_say.call_args_list[2][1]["text"] == "Generating proposal deck..."
            )
            assert mock_say.call_args_list[3][1]["text"] == "Proposal deck created"

            # Verify deck link is in the final message
            final_blocks = mock_say.call_args_list[3][1]["blocks"]
            deck_link_found = False
            for block in final_blocks:
                if block.get("type") == "section":
                    text = block.get("text", {}).get("text", "")
                    if deck_link in text:
                        deck_link_found = True
                        break
            assert deck_link_found, "Deck link not found in completion message"

            # ─────────────────────────────────────────────────────────────────
            # VERIFY: Both documents created
            # ─────────────────────────────────────────────────────────────────
            mock_docs.create_document.assert_called_once_with(
                "acme-corp - Deal Analysis",
                "folder_analyse_123",
            )
            populate_deal.assert_called_once()

            mock_slides.duplicate_template.assert_called_once_with(
                "acme-corp - Proposal",
                "folder_proposals_123",
            )
            populate_deck.assert_called_once()

            # ─────────────────────────────────────────────────────────────────
            # VERIFY: LLM called correctly for both phases
            # ─────────────────────────────────────────────────────────────────
            mock_llm.generate_deal_analysis.assert_called_once()
            mock_llm.generate_proposal_deck_content.assert_called_once_with(
                deal_analysis_response["deal_analysis"]
            )

            # ─────────────────────────────────────────────────────────────────
            # VERIFY: Complete state transition chain
            # ─────────────────────────────────────────────────────────────────
            events = [t["event"] for t in state_transitions]
            assert events == [
                Event.ANALYSE_REQUESTED,
                Event.DEAL_ANALYSIS_CREATED,
                Event.APPROVED,
                Event.DECK_CREATED,
            ], f"Unexpected state transition chain: {events}"
