"""Integration tests for the full Analyse -> Deal Analysis flow.

Tests the complete workflow from receiving an Analyse command with transcript
attachment through to Deal Analysis document creation and approval prompt.
All external APIs (Slack, Google Drive, Google Docs, LLM) are mocked.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.slack.handlers import handle_analyse_command
from proposal_assistant.state.models import Event

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def transcript_content():
    """Load valid transcript fixture."""
    transcript_path = FIXTURES_DIR / "transcripts" / "valid_transcript.md"
    return transcript_path.read_text()


@pytest.fixture
def llm_response():
    """Load LLM response fixture."""
    response_path = FIXTURES_DIR / "llm_responses" / "deal_analysis_response.json"
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
def mock_say():
    """Create a mock say function that tracks calls."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock Slack WebClient."""
    return MagicMock()


class TestFullAnalyseFlow:
    """Integration tests for the complete Analyse -> Deal Analysis flow."""

    def test_full_flow_creates_deal_analysis_and_prompts_approval(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
        llm_response,
    ):
        """Full flow: Analyse command creates Deal Analysis doc and shows approval buttons."""
        state_transitions = []

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
            patch(
                "proposal_assistant.slack.handlers.populate_deal_analysis"
            ) as populate,
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

            mock_state_machine.transition.side_effect = track_transition
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

            # Mock LLM response
            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": llm_response["deal_analysis"],
                "missing_info": llm_response["missing_info"],
                "raw_response": json.dumps(llm_response),
            }
            LLMClient.return_value = mock_llm

            # Mock Docs creation
            mock_docs = MagicMock()
            doc_id = "doc_deal_analysis_123"
            doc_link = f"https://docs.google.com/document/d/{doc_id}"
            mock_docs.create_document.return_value = (doc_id, doc_link)
            DocsClient.return_value = mock_docs

            # Execute the handler
            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify state transitions
            assert (
                len(state_transitions) == 2
            ), f"Expected 2 state transitions, got {len(state_transitions)}"

            # First transition: ANALYSE_REQUESTED
            first_transition = state_transitions[0]
            assert first_transition["event"] == Event.ANALYSE_REQUESTED
            assert first_transition["thread_ts"] == "1706500000.000001"
            assert first_transition["channel_id"] == "C_TEST_CHANNEL"
            assert first_transition["user_id"] == "U_TEST_USER"
            assert first_transition["input_transcript_file_ids"] == ["F_TEST_FILE"]

            # Second transition: DEAL_ANALYSIS_CREATED
            second_transition = state_transitions[1]
            assert second_transition["event"] == Event.DEAL_ANALYSIS_CREATED
            assert second_transition["client_name"] == "acme-corp"
            assert second_transition["client_folder_id"] == "folder_client_123"
            assert second_transition["analyse_folder_id"] == "folder_analyse_123"
            assert second_transition["proposals_folder_id"] == "folder_proposals_123"
            assert second_transition["deal_analysis_doc_id"] == doc_id
            assert second_transition["deal_analysis_link"] == doc_link
            assert (
                second_transition["deal_analysis_content"]
                == llm_response["deal_analysis"]
            )
            assert (
                second_transition["missing_info_items"] == llm_response["missing_info"]
            )

            # Verify messages sent
            assert mock_say.call_count == 2

            # First message: "Analyzing..."
            first_call = mock_say.call_args_list[0]
            assert first_call[1]["text"] == "Analyzing transcript..."
            assert first_call[1]["thread_ts"] == "1706500000.000001"

            # Second message: Deal Analysis complete with approval buttons
            second_call = mock_say.call_args_list[1]
            assert second_call[1]["text"] == "Deal Analysis created"
            blocks = second_call[1]["blocks"]

            # Verify doc link is in the message
            link_found = False
            for block in blocks:
                if block.get("type") == "section":
                    text = block.get("text", {}).get("text", "")
                    if doc_link in text:
                        link_found = True
                        break
            assert link_found, "Document link not found in message"

            # Verify approval buttons are present
            actions_block = next(
                (b for b in blocks if b.get("type") == "actions"),
                None,
            )
            assert actions_block is not None, "Approval buttons not found"
            assert actions_block["block_id"] == "approval_actions"

            button_ids = [e["action_id"] for e in actions_block["elements"]]
            assert "approve_deck" in button_ids
            assert "reject_deck" in button_ids

            # Verify external services were called correctly
            validate.assert_called_once()
            extract.assert_called_once_with("acme-corp-discovery-call.md")
            get_folders.assert_called_once()
            mock_llm.generate_deal_analysis.assert_called_once()
            mock_docs.create_document.assert_called_once_with(
                "acme-corp - Deal Analysis",
                "folder_analyse_123",
            )
            populate.assert_called_once()

    def test_full_flow_includes_missing_info_in_message(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
        llm_response,
    ):
        """Missing info from LLM response is displayed in the completion message."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch("proposal_assistant.slack.handlers.validate_transcript") as validate,
            patch("proposal_assistant.slack.handlers.StateMachine"),
            patch("proposal_assistant.slack.handlers.extract_client_name") as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme-corp"
            get_folders.return_value = {
                "client_folder_id": "c1",
                "analyse_folder_id": "a1",
                "proposals_folder_id": "p1",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": llm_response["deal_analysis"],
                "missing_info": ["Budget range", "Competing vendors"],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_id", "https://link")
            DocsClient.return_value = mock_docs

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Get the completion message blocks
            completion_call = mock_say.call_args_list[1]
            blocks = completion_call[1]["blocks"]

            # Find the missing info section
            missing_info_found = False
            for block in blocks:
                if block.get("type") == "section":
                    text = block.get("text", {}).get("text", "")
                    if "Missing information" in text or "Budget range" in text:
                        missing_info_found = True
                        assert "Budget range" in text or "Budget range" in str(blocks)
                        break

            assert missing_info_found, "Missing info not displayed in message"

    def test_full_flow_handles_no_missing_info(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
        llm_response,
    ):
        """Flow completes successfully when LLM returns no missing info."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch("proposal_assistant.slack.handlers.validate_transcript") as validate,
            patch("proposal_assistant.slack.handlers.StateMachine"),
            patch("proposal_assistant.slack.handlers.extract_client_name") as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme-corp"
            get_folders.return_value = {
                "client_folder_id": "c1",
                "analyse_folder_id": "a1",
                "proposals_folder_id": "p1",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": llm_response["deal_analysis"],
                "missing_info": [],  # No missing info
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_id", "https://link")
            DocsClient.return_value = mock_docs

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Should still complete successfully
            assert mock_say.call_count == 2
            completion_call = mock_say.call_args_list[1]
            assert completion_call[1]["text"] == "Deal Analysis created"


class TestFullFlowErrorHandling:
    """Integration tests for error handling in the full flow."""

    def test_llm_error_transitions_to_failed_state(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
    ):
        """LLM error during analysis transitions state to FAILED."""
        from proposal_assistant.llm.client import LLMError

        state_transitions = []

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
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)

            mock_state_machine = MagicMock()

            def track_transition(**kwargs):
                state_transitions.append(kwargs)

            mock_state_machine.transition.side_effect = track_transition
            StateMachine.return_value = mock_state_machine

            extract.return_value = "acme-corp"
            get_folders.return_value = {
                "client_folder_id": "c1",
                "analyse_folder_id": "a1",
                "proposals_folder_id": "p1",
            }

            # LLM raises error
            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.side_effect = LLMError(
                "Service unavailable", error_type="LLM_ERROR"
            )
            LLMClient.return_value = mock_llm

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify FAILED transition
            assert len(state_transitions) == 2
            failed_transition = state_transitions[1]
            assert failed_transition["event"] == Event.FAILED
            assert failed_transition["error_type"] == "LLM_ERROR"

            # Verify error message sent
            error_call = mock_say.call_args_list[-1]
            assert "AI service temporarily unavailable" in error_call[1]["text"]

    def test_drive_error_transitions_to_failed_state(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
    ):
        """Drive folder creation error transitions state to FAILED."""
        state_transitions = []

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
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)

            mock_state_machine = MagicMock()

            def track_transition(**kwargs):
                state_transitions.append(kwargs)

            mock_state_machine.transition.side_effect = track_transition
            StateMachine.return_value = mock_state_machine

            extract.return_value = "acme-corp"

            # Drive raises error
            get_folders.side_effect = Exception("Permission denied")

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify FAILED transition
            failed_transition = state_transitions[-1]
            assert failed_transition["event"] == Event.FAILED
            assert failed_transition["error_type"] == "DRIVE_PERMISSION"

            # Verify error message sent
            error_call = mock_say.call_args_list[-1]
            assert "Unable to access client folder" in error_call[1]["text"]

    def test_docs_error_transitions_to_failed_state(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
        llm_response,
    ):
        """Docs creation error transitions state to FAILED."""
        state_transitions = []

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
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)

            mock_state_machine = MagicMock()

            def track_transition(**kwargs):
                state_transitions.append(kwargs)

            mock_state_machine.transition.side_effect = track_transition
            StateMachine.return_value = mock_state_machine

            extract.return_value = "acme-corp"
            get_folders.return_value = {
                "client_folder_id": "c1",
                "analyse_folder_id": "a1",
                "proposals_folder_id": "p1",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": llm_response["deal_analysis"],
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            # Docs raises error
            mock_docs = MagicMock()
            mock_docs.create_document.side_effect = Exception("API quota exceeded")
            DocsClient.return_value = mock_docs

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify FAILED transition
            failed_transition = state_transitions[-1]
            assert failed_transition["event"] == Event.FAILED
            assert failed_transition["error_type"] == "DOCS_ERROR"

            # Verify error message sent
            error_call = mock_say.call_args_list[-1]
            assert "Failed to create Deal Analysis" in error_call[1]["text"]


class TestFullFlowStateVerification:
    """Tests verifying correct state data is stored throughout the flow."""

    def test_state_contains_all_required_data_for_approval(
        self,
        mock_say,
        mock_client,
        slack_message_with_file,
        mock_config,
        transcript_content,
        llm_response,
    ):
        """After Analyse flow, state contains all data needed for approval workflow."""
        captured_state_data = {}

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
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = transcript_content.encode("utf-8")
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            from proposal_assistant.utils.validation import ValidationResult

            validate.return_value = ValidationResult(is_valid=True)

            mock_state_machine = MagicMock()

            def capture_transition(**kwargs):
                if kwargs.get("event") == Event.DEAL_ANALYSIS_CREATED:
                    captured_state_data.update(kwargs)

            mock_state_machine.transition.side_effect = capture_transition
            StateMachine.return_value = mock_state_machine

            extract.return_value = "acme-corp"
            get_folders.return_value = {
                "client_folder_id": "folder_client_xyz",
                "analyse_folder_id": "folder_analyse_xyz",
                "proposals_folder_id": "folder_proposals_xyz",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": llm_response["deal_analysis"],
                "missing_info": llm_response["missing_info"],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_xyz",
                "https://docs.google.com/document/d/doc_xyz",
            )
            DocsClient.return_value = mock_docs

            handle_analyse_command(slack_message_with_file, mock_say, mock_client)

            # Verify all required fields for approval are present
            assert "client_name" in captured_state_data
            assert captured_state_data["client_name"] == "acme-corp"

            assert "proposals_folder_id" in captured_state_data
            assert captured_state_data["proposals_folder_id"] == "folder_proposals_xyz"

            assert "deal_analysis_content" in captured_state_data
            assert (
                captured_state_data["deal_analysis_content"]
                == llm_response["deal_analysis"]
            )

            assert "deal_analysis_doc_id" in captured_state_data
            assert captured_state_data["deal_analysis_doc_id"] == "doc_xyz"

            assert "deal_analysis_link" in captured_state_data
            assert "doc_xyz" in captured_state_data["deal_analysis_link"]

            # These are required for handle_approval to work
            assert captured_state_data["proposals_folder_id"] is not None
            assert captured_state_data["deal_analysis_content"] is not None
