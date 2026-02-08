"""Unit tests for cloud fallback flow.

Tests the complete flow:
1. Ollama health check fails (LLM_OFFLINE)
2. Cloud consent UI is shown
3. User accepts consent -> cloud AI is used
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.config import Config
from proposal_assistant.llm.client import LLMClient, LLMError
from proposal_assistant.slack.handlers import (
    handle_analyse_command,
    handle_cloud_consent_yes,
)
from proposal_assistant.slack.messages import ERROR_MESSAGES
from proposal_assistant.state.models import Event, State, ThreadState


@pytest.fixture
def mock_config_with_cloud():
    """Create a Config with cloud provider enabled."""
    return Config(
        slack_bot_token="xoxb-test",
        slack_app_token="xapp-test",
        slack_signing_secret="secret",
        google_service_account_json="{}",
        google_drive_root_folder_id="folder",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:14b",
        proposal_template_slide_id="slide",
        ollama_num_ctx=32768,
        cloud_provider="openai",
        openai_api_key="sk-test-key",
        openai_model="gpt-4o",
    )


@pytest.fixture
def mock_config_without_cloud():
    """Create a Config without cloud provider."""
    return Config(
        slack_bot_token="xoxb-test",
        slack_app_token="xapp-test",
        slack_signing_secret="secret",
        google_service_account_json="{}",
        google_drive_root_folder_id="folder",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:14b",
        proposal_template_slide_id="slide",
        ollama_num_ctx=32768,
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


class TestLLMClientCloudAvailability:
    """Tests for LLMClient cloud availability detection."""

    def test_cloud_available_when_openai_configured(self, mock_config_with_cloud):
        """Cloud is available when OpenAI is configured."""
        with patch("proposal_assistant.llm.client.OpenAI"):
            client = LLMClient(mock_config_with_cloud)
            assert client.cloud_available is True

    def test_cloud_not_available_when_not_configured(self, mock_config_without_cloud):
        """Cloud is not available when no cloud provider is configured."""
        with patch("proposal_assistant.llm.client.OpenAI"):
            client = LLMClient(mock_config_without_cloud)
            assert client.cloud_available is False

    def test_cloud_not_available_when_no_api_key(self):
        """Cloud is not available when API key is missing."""
        config = Config(
            slack_bot_token="xoxb-test",
            slack_app_token="xapp-test",
            slack_signing_secret="secret",
            google_service_account_json="{}",
            google_drive_root_folder_id="folder",
            ollama_base_url="http://localhost:11434/v1",
            ollama_model="qwen2.5:14b",
            proposal_template_slide_id="slide",
            cloud_provider="openai",
            openai_api_key=None,  # No API key
        )
        with patch("proposal_assistant.llm.client.OpenAI"):
            client = LLMClient(config)
            assert client.cloud_available is False


class TestOllamaOfflineShowsCloudConsent:
    """Tests for showing cloud consent when Ollama is offline."""

    def test_llm_offline_with_cloud_available_shows_consent(
        self, mock_say, mock_client, analyse_message, mock_config_with_cloud
    ):
        """When LLM is offline and cloud is available, show consent buttons."""
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
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
        ):
            from proposal_assistant.utils.validation import ValidationResult

            get_config.return_value = mock_config_with_cloud

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
            }

            # Mock LLM to raise LLM_OFFLINE error
            mock_llm = MagicMock()
            mock_llm.cloud_available = True
            mock_llm.generate_deal_analysis.side_effect = LLMError(
                "Cannot connect to LLM service",
                error_type="LLM_OFFLINE",
            )
            LLMClientMock.return_value = mock_llm

            handle_analyse_command(analyse_message, mock_say, mock_client)

        # Should have called say twice: "Analyzing..." and cloud consent
        assert mock_say.call_count == 2

        # Second call should be cloud consent message
        second_call = mock_say.call_args_list[1][1]
        assert second_call["text"] == "Local AI unavailable. Use cloud?"
        assert any(
            block.get("block_id") == "cloud_consent_actions"
            for block in second_call["blocks"]
        )

    def test_llm_offline_without_cloud_shows_error(
        self, mock_say, mock_client, analyse_message, mock_config_without_cloud
    ):
        """When LLM is offline and cloud is not available, show error message."""
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
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
        ):
            from proposal_assistant.utils.validation import ValidationResult

            get_config.return_value = mock_config_without_cloud

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
            }

            # Mock LLM to raise LLM_OFFLINE error, cloud not available
            mock_llm = MagicMock()
            mock_llm.cloud_available = False
            mock_llm.generate_deal_analysis.side_effect = LLMError(
                "Cannot connect to LLM service",
                error_type="LLM_OFFLINE",
            )
            LLMClientMock.return_value = mock_llm

            handle_analyse_command(analyse_message, mock_say, mock_client)

        # Second call should be error message, not consent
        second_call = mock_say.call_args_list[1][1]
        assert second_call["text"] == ERROR_MESSAGES["LLM_OFFLINE"]
        assert "cloud_consent_actions" not in str(second_call["blocks"])


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
            input_transcript_content=[
                "# Meeting transcript\n\nDiscussion about Acme Corp."
            ],
            error_type="LLM_OFFLINE",
        )

    def test_cloud_consent_yes_uses_cloud_llm(
        self,
        mock_say,
        mock_client,
        cloud_consent_body,
        mock_config_with_cloud,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent calls LLM with use_cloud=True."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config_with_cloud
            StateMachine.return_value.get_state.return_value = (
                mock_thread_state_for_cloud
            )

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": [],
            }
            LLMClientMock.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_123",
                "https://docs.google.com/doc",
            )
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Verify LLM was called with use_cloud=True
        mock_llm.generate_deal_analysis.assert_called_once()
        call_kwargs = mock_llm.generate_deal_analysis.call_args[1]
        assert call_kwargs["use_cloud"] is True
        assert call_kwargs["transcript"] == [
            "# Meeting transcript\n\nDiscussion about Acme Corp."
        ]

    def test_cloud_consent_yes_transitions_with_cloud_consent_given(
        self,
        mock_say,
        mock_client,
        cloud_consent_body,
        mock_config_with_cloud,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent sets cloud_consent_given=True in state."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config_with_cloud
            StateMachine.return_value.get_state.return_value = (
                mock_thread_state_for_cloud
            )

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClientMock.return_value = mock_llm

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
        mock_config_with_cloud,
        mock_thread_state_for_cloud,
    ):
        """Accepting cloud consent completes deal analysis flow."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config_with_cloud
            StateMachine.return_value.get_state.return_value = (
                mock_thread_state_for_cloud
            )

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": ["Budget range"],
            }
            LLMClientMock.return_value = mock_llm

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
        assert any(
            block.get("block_id") == "approval_actions"
            for block in second_call["blocks"]
        )


class TestLLMClientCloudCalls:
    """Tests for LLMClient cloud API calls."""

    def test_generate_with_use_cloud_calls_cloud_client(self, mock_config_with_cloud):
        """generate() with use_cloud=True uses cloud client."""
        with patch("proposal_assistant.llm.client.OpenAI") as MockOpenAI:
            # Create separate mock instances for local and cloud
            mock_local = MagicMock()
            mock_cloud = MagicMock()

            # Configure return values
            mock_cloud_response = MagicMock()
            mock_cloud_response.choices = [MagicMock()]
            mock_cloud_response.choices[0].message.content = '{"test": "response"}'
            mock_cloud.chat.completions.create.return_value = mock_cloud_response

            # First call creates local client, second creates cloud client
            MockOpenAI.side_effect = [mock_local, mock_cloud]

            client = LLMClient(mock_config_with_cloud)

            result = client.generate(
                [{"role": "user", "content": "test"}],
                use_cloud=True,
            )

        assert result == '{"test": "response"}'
        mock_cloud.chat.completions.create.assert_called_once()
        mock_local.chat.completions.create.assert_not_called()

    def test_generate_without_use_cloud_uses_local(self, mock_config_with_cloud):
        """generate() without use_cloud uses local Ollama client."""
        with patch("proposal_assistant.llm.client.OpenAI") as MockOpenAI:
            mock_local = MagicMock()
            mock_cloud = MagicMock()

            mock_local_response = MagicMock()
            mock_local_response.choices = [MagicMock()]
            mock_local_response.choices[0].message.content = '{"local": "response"}'
            mock_local_response.usage = None
            mock_local.chat.completions.create.return_value = mock_local_response

            MockOpenAI.side_effect = [mock_local, mock_cloud]

            client = LLMClient(mock_config_with_cloud)

            result = client.generate(
                [{"role": "user", "content": "test"}],
                use_cloud=False,
            )

        assert result == '{"local": "response"}'
        mock_local.chat.completions.create.assert_called_once()
        mock_cloud.chat.completions.create.assert_not_called()

    def test_cloud_call_raises_error_when_not_configured(
        self, mock_config_without_cloud
    ):
        """Calling cloud when not configured raises LLMError."""
        with patch("proposal_assistant.llm.client.OpenAI") as MockOpenAI:
            mock_local = MagicMock()
            MockOpenAI.return_value = mock_local

            client = LLMClient(mock_config_without_cloud)

            with pytest.raises(LLMError, match="Cloud provider not configured"):
                client.generate(
                    [{"role": "user", "content": "test"}],
                    use_cloud=True,
                )

    def test_generate_deal_analysis_passes_use_cloud(self, mock_config_with_cloud):
        """generate_deal_analysis() passes use_cloud to generate()."""
        with patch("proposal_assistant.llm.client.OpenAI") as MockOpenAI:
            mock_local = MagicMock()
            mock_cloud = MagicMock()

            mock_cloud_response = MagicMock()
            mock_cloud_response.choices = [MagicMock()]
            mock_cloud_response.choices[0].message.content = json.dumps(
                {
                    "deal_analysis": {"company": "Test Corp"},
                    "missing_info": [],
                }
            )
            mock_cloud.chat.completions.create.return_value = mock_cloud_response

            MockOpenAI.side_effect = [mock_local, mock_cloud]

            client = LLMClient(mock_config_with_cloud)

            result = client.generate_deal_analysis(
                transcript="Test transcript",
                use_cloud=True,
            )

        assert result["content"]["company"] == "Test Corp"
        mock_cloud.chat.completions.create.assert_called_once()


class TestEndToEndCloudFallbackFlow:
    """Integration-style tests for the complete cloud fallback flow."""

    def test_full_flow_ollama_offline_to_cloud_success(
        self, mock_say, mock_client, analyse_message, mock_config_with_cloud
    ):
        """Test complete flow: Ollama offline -> consent shown -> cloud used."""
        # Step 1: Initial analyse command fails with LLM_OFFLINE
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
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
        ):
            from proposal_assistant.utils.validation import ValidationResult

            get_config.return_value = mock_config_with_cloud

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
            }

            mock_llm = MagicMock()
            mock_llm.cloud_available = True
            mock_llm.generate_deal_analysis.side_effect = LLMError(
                "Cannot connect",
                error_type="LLM_OFFLINE",
            )
            LLMClientMock.return_value = mock_llm

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

        # Verify cloud consent was shown
        consent_call = mock_say.call_args_list[1][1]
        assert consent_call["text"] == "Local AI unavailable. Use cloud?"

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
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClientMock,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config_with_cloud
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
                "missing_info": [],
            }
            LLMClientMock.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = (
                "doc_123",
                "https://docs.google.com/doc",
            )
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Verify cloud was used
        mock_llm.generate_deal_analysis.assert_called_once()
        call_kwargs = mock_llm.generate_deal_analysis.call_args[1]
        assert call_kwargs["use_cloud"] is True

        # Verify deal analysis was completed
        completion_call = mock_say.call_args_list[1][1]
        assert completion_call["text"] == "Deal Analysis created"
