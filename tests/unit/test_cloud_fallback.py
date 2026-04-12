"""Unit tests for cloud fallback flow.

With the migration to Anthropic SDK, the "cloud fallback" concept is simplified:
- Claude IS the cloud backend, so cloud_available is always True
- The LLM uses generate_deal_analysis() / generate_proposal_content() functions
- No more LLMClient class or use_cloud parameter
"""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.config import Config
from proposal_assistant.llm.agent import LLMError
from proposal_assistant.slack.handlers import (
    handle_analyse_command,
    handle_cloud_consent_yes,
)
from proposal_assistant.slack.messages import ERROR_MESSAGES
from proposal_assistant.state.models import Event, State, ThreadState


@pytest.fixture
def mock_config():
    """Create a Config with Anthropic."""
    return Config(
        slack_bot_token="xoxb-test",
        slack_app_token="xapp-test",
        slack_signing_secret="secret",
        google_service_account_json="{}",
        google_drive_root_folder_id="folder",
        anthropic_api_key="sk-ant-test-key",
        proposal_template_slide_id="slide",
    )


@pytest.fixture
def mock_say():
    """Create a mock say function."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock Slack WebClient."""
    return MagicMock()


@pytest.fixture
def analyse_message():
    """Create a Slack message payload with file attachment."""
    return {
        "ts": "1706440000.000001",
        "channel": "C1234567890",
        "channel_type": "channel",
        "user": "U1234567890",
        "text": "Analyse",
        "files": [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ],
    }


@pytest.fixture
def cloud_consent_body():
    """Create a Slack action payload for cloud consent button click."""
    return {
        "channel": {"id": "C1234567890"},
        "message": {"ts": "1706440000.000001", "thread_ts": "1706430000.000000"},
        "user": {"id": "U1234567890"},
    }


class TestLLMOfflineShowsError:
    """Tests for showing error when LLM is offline."""

    def test_llm_offline_shows_error_message(
        self, mock_say, mock_client, analyse_message, mock_config
    ):
        """When LLM raises LLM_OFFLINE error, show error message to user."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.validate_transcript") as validate,
            patch("proposal_assistant.slack.handlers.StateMachine"),
            patch("proposal_assistant.slack.handlers.extract_client_name") as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.get_or_create_client_folder") as get_folders,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
        ):
            from proposal_assistant.utils.validation import ValidationResult

            get_config.return_value = mock_config

            # Mock file download
            mock_response = MagicMock()
            mock_response.read.return_value = b"# Meeting Transcript\n\nContent here."
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme"
            get_folders.return_value = {
                "client_folder_id": "client_123",
                "analyse_folder_id": "analyse_123",
                "proposals_folder_id": "proposals_123",
                "meetings_folder_id": "meetings_123",
            }

            # Mock LLM to raise LLM_OFFLINE error
            mock_generate_deal.side_effect = LLMError(
                "Cannot connect to LLM service",
                error_type="LLM_OFFLINE",
            )

            handle_analyse_command(analyse_message, mock_say, mock_client)

        # Should have called say twice: "Analyzing..." and error message
        assert mock_say.call_count == 2

        # Second call should be the LLM_OFFLINE error message
        second_call = mock_say.call_args_list[1][1]
        assert second_call["text"] == ERROR_MESSAGES["LLM_OFFLINE"]


class TestCloudConsentAcceptedUsesCloud:
    """Tests for using cloud AI when consent is accepted."""

    @pytest.fixture
    def mock_thread_state_for_cloud(self):
        """Mock thread state with stored transcript for cloud retry."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.ERROR,
            client_name="acme",
            channel_type="channel",
            analyse_folder_id="analyse_123",
            proposals_folder_id="proposals_123",
            input_transcript_content=["# Meeting transcript\n\nDiscussion about Acme Corp."],
            error_type="LLM_OFFLINE",
        )

    def test_cloud_consent_yes_calls_generate_deal_analysis(
        self,
        mock_say,
        mock_client,
        cloud_consent_body,
        mock_config,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent calls generate_deal_analysis with transcript."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_cloud

            mock_generate_deal.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": [],
            }

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_123",
                "https://docs.google.com/doc",
            )
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Verify generate_deal_analysis was called with the transcript
        mock_generate_deal.assert_called_once()
        call_kwargs = mock_generate_deal.call_args[1]
        assert call_kwargs["transcript"] == ["# Meeting transcript\n\nDiscussion about Acme Corp."]

    def test_cloud_consent_yes_transitions_with_cloud_consent_given(
        self,
        mock_say,
        mock_client,
        cloud_consent_body,
        mock_config,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent sets cloud_consent_given=True in state."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_cloud

            mock_generate_deal.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_123", "link")
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list

        # First transition should be CLOUD_CONSENT_GIVEN with cloud_consent_given=True
        first_call = calls[0]
        assert first_call[1]["event"] == Event.CLOUD_CONSENT_GIVEN
        assert first_call[1]["cloud_consent_given"] is True

    def test_cloud_consent_yes_completes_deal_analysis(
        self,
        mock_say,
        mock_client,
        cloud_consent_body,
        mock_config,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent completes deal analysis flow."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_cloud

            mock_generate_deal.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": ["Budget range"],
            }

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_123",
                "https://docs.google.com/document/d/doc_123",
            )
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Should send analyzing message and completion message with approval buttons
        assert mock_say.call_count == 2

        # First call: "Analyzing..."
        first_call = mock_say.call_args_list[0][1]
        assert first_call["text"] == "Analyzing transcript..."

        # Second call: completion with approval buttons
        second_call = mock_say.call_args_list[1][1]
        assert second_call["text"] == "Deal Analysis created"
        assert any(block.get("block_id") == "approval_actions" for block in second_call["blocks"])


class TestEndToEndCloudFallbackFlow:
    """Integration-style tests for the complete cloud fallback flow."""

    def test_full_flow_llm_offline_to_cloud_success(
        self, mock_say, mock_client, analyse_message, mock_config
    ):
        """Test complete flow: LLM offline -> error shown -> cloud consent -> success."""
        # Step 1: Initial analyse command fails with LLM_OFFLINE
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.validate_transcript") as validate,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.extract_client_name") as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.get_or_create_client_folder") as get_folders,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
        ):
            from proposal_assistant.utils.validation import ValidationResult

            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = b"# Meeting Transcript"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme"
            get_folders.return_value = {
                "client_folder_id": "client_123",
                "analyse_folder_id": "analyse_123",
                "proposals_folder_id": "proposals_123",
                "meetings_folder_id": "meetings_123",
            }

            mock_generate_deal.side_effect = LLMError(
                "Cannot connect",
                error_type="LLM_OFFLINE",
            )

            handle_analyse_command(analyse_message, mock_say, mock_client)

            # Verify state was transitioned to ERROR with LLM_OFFLINE
            state_machine = StateMachine.return_value
            failed_call = [
                call
                for call in state_machine.transition.call_args_list
                if call[1].get("event") == Event.FAILED
            ]
            assert len(failed_call) == 1
            assert failed_call[0][1]["error_type"] == "LLM_OFFLINE"

        # Verify error message was shown (not cloud consent)
        error_call = mock_say.call_args_list[1][1]
        assert error_call["text"] == ERROR_MESSAGES["LLM_OFFLINE"]

        # Step 2: User accepts cloud consent
        mock_say.reset_mock()

        cloud_consent_body = {
            "channel": {"id": "C1234567890"},
            "message": {"ts": "1706440000.000001", "thread_ts": "1706440000.000001"},
            "user": {"id": "U1234567890"},
        }

        mock_thread_state = ThreadState(
            thread_ts="1706440000.000001",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.ERROR,
            client_name="acme",
            channel_type="channel",
            analyse_folder_id="analyse_123",
            proposals_folder_id="proposals_123",
            input_transcript_content=["# Meeting Transcript"],
            error_type="LLM_OFFLINE",
        )

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.generate_deal_analysis") as mock_generate_deal,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_generate_deal.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": [],
            }

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_123",
                "https://docs.google.com/doc",
            )
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Verify generate_deal_analysis was called (no use_cloud param)
        mock_generate_deal.assert_called_once()

        # Verify deal analysis was completed
        completion_call = mock_say.call_args_list[1][1]
        assert completion_call["text"] == "Deal Analysis created"
