"""Unit tests for Slack handlers module."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.slack.handlers import (
    handle_analyse_command,
    handle_approval,
    handle_cloud_consent_no,
    handle_cloud_consent_yes,
    handle_rejection,
    handle_updated_deal_analysis,
)
from proposal_assistant.slack.messages import ERROR_MESSAGES
from proposal_assistant.state.models import State, ThreadState
from proposal_assistant.utils.validation import ValidationResult


@pytest.fixture
def mock_say():
    """Create a mock say function."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock Slack WebClient."""
    return MagicMock()


@pytest.fixture
def base_message():
    """Create a base Slack message payload."""
    return {
        "ts": "1706440000.000001",
        "channel": "C1234567890",
        "user": "U1234567890",
        "text": "Analyse",
    }


@pytest.fixture
def mock_config():
    """Create a mock Config object."""
    config = MagicMock()
    config.slack_bot_token = "xoxb-test-token"
    config.google_service_account_json = '{"type": "service_account"}'
    config.google_drive_root_folder_id = "root_folder_id"
    config.ollama_base_url = "http://localhost:11434"
    config.ollama_model = "test-model"
    return config


@pytest.fixture
def mock_all_dependencies(mock_config):
    """Mock all external dependencies for a successful workflow."""
    with (
        patch("proposal_assistant.slack.handlers.get_config") as get_config,
        patch("proposal_assistant.slack.handlers.urllib.request.Request"),
        patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
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
        # Configure mocks
        get_config.return_value = mock_config

        # Mock file download
        mock_response = MagicMock()
        mock_response.read.return_value = b"# Meeting Transcript\n\nContent here."
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        urlopen.return_value = mock_response

        # Mock validation
        validate.return_value = ValidationResult(is_valid=True)

        # Mock client name extraction
        extract.return_value = "acme"

        # Mock folder creation
        get_folders.return_value = {
            "client_folder_id": "client_123",
            "meetings_folder_id": "meetings_123",
            "analyse_folder_id": "analyse_123",
            "proposals_folder_id": "proposals_123",
            "references_folder_id": "references_123",
        }

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.generate_deal_analysis.return_value = {
            "content": {"opportunity_snapshot": {"company": "Acme Corp"}},
            "missing_info": ["budget", "timeline"],
            "raw_response": "{}",
        }
        LLMClient.return_value = mock_llm

        # Mock Docs
        mock_docs = MagicMock()
        mock_docs.create_document.return_value = (
            "doc_123",
            "https://docs.google.com/document/d/doc_123",
        )
        DocsClient.return_value = mock_docs

        yield {
            "get_config": get_config,
            "urlopen": urlopen,
            "validate": validate,
            "StateMachine": StateMachine,
            "extract_client_name": extract,
            "get_folders": get_folders,
            "LLMClient": LLMClient,
            "DocsClient": DocsClient,
        }


class TestHandleAnalyseCommand:
    """Tests for handle_analyse_command function."""

    def test_analyse_without_file_shows_error(
        self, mock_say, mock_client, base_message
    ):
        """Analyse command without file attachment shows INPUT_MISSING error."""
        handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_MISSING"]
        assert call_kwargs["thread_ts"] == "1706440000.000001"

    def test_analyse_with_empty_files_list_shows_error(
        self, mock_say, mock_client, base_message
    ):
        """Analyse command with empty files list shows INPUT_MISSING error."""
        base_message["files"] = []

        handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_MISSING"]

    def test_uses_thread_ts_when_in_thread(
        self, mock_say, mock_client, base_message
    ):
        """Handler uses thread_ts for replies when message is in a thread."""
        base_message["thread_ts"] = "1706430000.000000"

        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706430000.000000"

    def test_uses_ts_when_not_in_thread(
        self, mock_say, mock_client, base_message
    ):
        """Handler uses message ts for replies when not in a thread."""
        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706440000.000001"

    def test_error_reply_includes_blocks(self, mock_say, mock_client, base_message):
        """Error reply includes Block Kit blocks."""
        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert "blocks" in call_kwargs
        assert isinstance(call_kwargs["blocks"], list)


class TestHandleAnalyseCommandNoFileReturnsEarly:
    """Tests verifying handler returns early on missing file."""

    def test_no_file_does_not_continue_workflow(
        self, mock_say, mock_client, base_message
    ):
        """Without file, handler returns after error and doesn't continue."""
        handle_analyse_command(base_message, mock_say, mock_client)

        assert mock_say.call_count == 1
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_MISSING"]


class TestHandleAnalyseCommandHappyPath:
    """Tests for the full successful workflow."""

    def test_full_workflow_sends_completion_message(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Successful workflow sends completion message with approval buttons."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        # Should have called say twice: "Analyzing..." and completion
        assert mock_say.call_count == 2

        # First call is "Analyzing..."
        first_call = mock_say.call_args_list[0][1]
        assert first_call["text"] == "Analyzing transcript..."

        # Second call is completion with approval buttons
        second_call = mock_say.call_args_list[1][1]
        assert "Deal Analysis created" in second_call["text"]
        # Blocks should include approval buttons
        assert any(
            block.get("block_id") == "approval_actions"
            for block in second_call["blocks"]
        )

    def test_transitions_to_generating_deal_analysis(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Handler transitions state to GENERATING_DEAL_ANALYSIS."""
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        state_machine = mock_all_dependencies["StateMachine"].return_value
        calls = state_machine.transition.call_args_list

        # First transition should be ANALYSE_REQUESTED
        first_call = calls[0]
        assert first_call[1]["event"] == Event.ANALYSE_REQUESTED

    def test_transitions_to_waiting_for_approval(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Handler transitions state to WAITING_FOR_APPROVAL after doc creation."""
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        state_machine = mock_all_dependencies["StateMachine"].return_value
        calls = state_machine.transition.call_args_list

        # Second transition should be DEAL_ANALYSIS_CREATED
        second_call = calls[1]
        assert second_call[1]["event"] == Event.DEAL_ANALYSIS_CREATED
        assert second_call[1]["client_name"] == "acme"
        assert second_call[1]["deal_analysis_doc_id"] == "doc_123"

    def test_creates_drive_folders(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Handler creates Drive folder structure for client."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        mock_all_dependencies["get_folders"].assert_called_once()
        call_args = mock_all_dependencies["get_folders"].call_args[0]
        assert call_args[1] == "acme"  # client_name

    def test_calls_llm_with_transcript(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Handler calls LLM with downloaded transcript content."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        llm_instance = mock_all_dependencies["LLMClient"].return_value
        llm_instance.generate_deal_analysis.assert_called_once()
        call_kwargs = llm_instance.generate_deal_analysis.call_args[1]
        # transcript is now passed as a list
        assert isinstance(call_kwargs["transcript"], list)
        assert len(call_kwargs["transcript"]) == 1
        assert "Meeting Transcript" in call_kwargs["transcript"][0]

    def test_creates_google_doc_in_analyse_folder(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Handler creates Google Doc in the Analyse folder."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        docs_instance = mock_all_dependencies["DocsClient"].return_value
        docs_instance.create_document.assert_called_once()
        call_args = docs_instance.create_document.call_args[0]
        assert call_args[0] == "acme - Deal Analysis"  # title
        assert call_args[1] == "analyse_123"  # folder_id


class TestHandleAnalyseCommandMultipleFiles:
    """Tests for multiple file handling."""

    def test_multiple_md_files_merges_content(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Multiple .md files are merged in order with separator."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting1.md",
                "url_private_download": "https://slack.com/files/1",
            },
            {
                "id": "F456",
                "name": "acme-meeting2.md",
                "url_private_download": "https://slack.com/files/2",
            },
        ]

        # Mock different responses for each file
        responses = [b"# Meeting 1 content", b"# Meeting 2 content"]
        call_count = [0]

        def mock_urlopen(req):
            mock_response = MagicMock()
            mock_response.read.return_value = responses[call_count[0]]
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            call_count[0] += 1
            return mock_response

        mock_all_dependencies["urlopen"].side_effect = mock_urlopen

        handle_analyse_command(base_message, mock_say, mock_client)

        # Verify LLM was called with list of transcripts
        llm_instance = mock_all_dependencies["LLMClient"].return_value
        call_kwargs = llm_instance.generate_deal_analysis.call_args[1]
        # transcript is now passed as a list - merging happens in context_builder
        assert isinstance(call_kwargs["transcript"], list)
        assert len(call_kwargs["transcript"]) == 2
        assert "Meeting 1 content" in call_kwargs["transcript"][0]
        assert "Meeting 2 content" in call_kwargs["transcript"][1]

    def test_multiple_files_tracks_all_file_ids(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """All file IDs are tracked in state transition."""
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting1.md",
                "url_private_download": "https://slack.com/files/1",
            },
            {
                "id": "F456",
                "name": "acme-meeting2.md",
                "url_private_download": "https://slack.com/files/2",
            },
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        state_machine = mock_all_dependencies["StateMachine"].return_value
        calls = state_machine.transition.call_args_list
        first_call = calls[0]
        assert first_call[1]["event"] == Event.ANALYSE_REQUESTED
        assert first_call[1]["input_transcript_file_ids"] == ["F123", "F456"]

    def test_non_md_files_are_filtered_out(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Non-.md files are ignored; only .md files are processed."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/1",
            },
            {
                "id": "F456",
                "name": "image.png",
                "url_private_download": "https://slack.com/files/2",
            },
            {
                "id": "F789",
                "name": "doc.pdf",
                "url_private_download": "https://slack.com/files/3",
            },
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        # Only F123 should be tracked
        state_machine = mock_all_dependencies["StateMachine"].return_value
        calls = state_machine.transition.call_args_list
        first_call = calls[0]
        assert first_call[1]["input_transcript_file_ids"] == ["F123"]

    def test_only_non_md_files_shows_error(
        self, mock_say, mock_client, base_message
    ):
        """If no .md files present, shows INPUT_INVALID error."""
        base_message["files"] = [
            {"id": "F123", "name": "image.png", "url_private_download": "https://..."},
            {"id": "F456", "name": "doc.pdf", "url_private_download": "https://..."},
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_INVALID"]

    def test_client_name_from_first_file(
        self, mock_say, mock_client, base_message, mock_all_dependencies
    ):
        """Client name is extracted from the first .md file."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "alpha-meeting.md",
                "url_private_download": "https://slack.com/files/1",
            },
            {
                "id": "F456",
                "name": "beta-meeting.md",
                "url_private_download": "https://slack.com/files/2",
            },
        ]

        mock_all_dependencies["extract_client_name"].return_value = "alpha"

        handle_analyse_command(base_message, mock_say, mock_client)

        mock_all_dependencies["extract_client_name"].assert_called_with("alpha-meeting.md")


class TestHandleAnalyseCommandErrorPaths:
    """Tests for error handling in the workflow."""

    def test_missing_download_url_shows_error(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """Missing download URL shows INPUT_INVALID error."""
        base_message["files"] = [
            {"id": "F123", "name": "test.md"}  # No url_private_download
        ]

        with patch("proposal_assistant.slack.handlers.get_config") as get_config:
            get_config.return_value = mock_config
            handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_INVALID"]

    def test_download_failure_shows_error(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """File download failure shows INPUT_INVALID error."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "test.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
        ):
            get_config.return_value = mock_config
            urlopen.side_effect = Exception("Network error")

            handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_INVALID"]

    def test_invalid_transcript_shows_error(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """Invalid transcript validation shows INPUT_INVALID error."""
        base_message["files"] = [
            {
                "id": "F123",
                "name": "test.txt",  # Wrong extension
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch(
                "proposal_assistant.slack.handlers.validate_transcript"
            ) as validate,
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(
                is_valid=False,
                error_type="invalid_extension",
                error_message="Must be .md",
            )

            handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_INVALID"]

    def test_drive_error_shows_error_and_transitions_to_failed(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """Drive folder creation error shows error and transitions to FAILED."""
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch(
                "proposal_assistant.slack.handlers.validate_transcript"
            ) as validate,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch(
                "proposal_assistant.slack.handlers.extract_client_name"
            ) as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme"
            get_folders.side_effect = Exception("Drive API error")

            handle_analyse_command(base_message, mock_say, mock_client)

        # Should have 2 calls: "Analyzing..." and error
        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["DRIVE_PERMISSION"]

        # Check state transition to FAILED
        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)

    def test_llm_error_shows_error_and_transitions_to_failed(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """LLM error shows error message and transitions to FAILED."""
        from proposal_assistant.llm.client import LLMError
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch(
                "proposal_assistant.slack.handlers.validate_transcript"
            ) as validate,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch(
                "proposal_assistant.slack.handlers.extract_client_name"
            ) as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme"
            get_folders.return_value = {
                "client_folder_id": "client_123",
                "analyse_folder_id": "analyse_123",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.side_effect = LLMError(
                "API unavailable", error_type="LLM_ERROR"
            )
            LLMClient.return_value = mock_llm

            handle_analyse_command(base_message, mock_say, mock_client)

        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["LLM_ERROR"]

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)

    def test_docs_error_shows_error_and_transitions_to_failed(
        self, mock_say, mock_client, base_message, mock_config
    ):
        """Docs creation error shows error and transitions to FAILED."""
        from proposal_assistant.state.models import Event

        base_message["files"] = [
            {
                "id": "F123",
                "name": "acme-meeting.md",
                "url_private_download": "https://slack.com/files/...",
            }
        ]

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch(
                "proposal_assistant.slack.handlers.urllib.request.urlopen"
            ) as urlopen,
            patch(
                "proposal_assistant.slack.handlers.validate_transcript"
            ) as validate,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch(
                "proposal_assistant.slack.handlers.extract_client_name"
            ) as extract,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch(
                "proposal_assistant.slack.handlers.get_or_create_client_folder"
            ) as get_folders,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
        ):
            get_config.return_value = mock_config

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            validate.return_value = ValidationResult(is_valid=True)
            extract.return_value = "acme"
            get_folders.return_value = {
                "client_folder_id": "client_123",
                "analyse_folder_id": "analyse_123",
            }

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.side_effect = Exception("Docs API error")
            DocsClient.return_value = mock_docs

            handle_analyse_command(base_message, mock_say, mock_client)

        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["DOCS_ERROR"]

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)


@pytest.fixture
def approval_body():
    """Create a Slack action payload for approval button click."""
    return {
        "channel": {"id": "C1234567890"},
        "message": {"ts": "1706440000.000001", "thread_ts": "1706430000.000000"},
        "user": {"id": "U1234567890"},
    }


@pytest.fixture
def mock_thread_state():
    """Create a mock ThreadState with required data for approval."""
    state = ThreadState(
        thread_ts="1706430000.000000",
        channel_id="C1234567890",
        user_id="U1234567890",
        state=State.WAITING_FOR_APPROVAL,
        client_name="acme",
        proposals_folder_id="proposals_123",
        deal_analysis_content={"opportunity_snapshot": {"company": "Acme Corp"}},
    )
    return state


class TestHandleApproval:
    """Tests for handle_approval function."""

    def test_approval_sends_generating_message(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Approval sends 'Generating proposal deck...' message."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {"center_title": "Acme Proposal"}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = (
                "deck_123",
                "https://docs.google.com/presentation/d/deck_123",
            )
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        # First call should be "Generating..."
        first_call = mock_say.call_args_list[0][1]
        assert first_call["text"] == "Generating proposal deck..."

    def test_approval_transitions_to_generating_deck(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Approval transitions state to GENERATING_DECK."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        first_call = calls[0]
        assert first_call[1]["event"] == Event.APPROVED

    def test_approval_creates_slides_deck(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Approval creates Google Slides presentation."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        mock_slides.duplicate_template.assert_called_once()
        call_args = mock_slides.duplicate_template.call_args[0]
        assert call_args[0] == "acme - Proposal"
        assert call_args[1] == "proposals_123"

    def test_approval_sends_completion_message(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Approval sends completion message with deck link."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = (
                "deck_123",
                "https://docs.google.com/presentation/d/deck_123",
            )
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        # Second call should be completion message
        second_call = mock_say.call_args_list[1][1]
        assert second_call["text"] == "Proposal deck created"

    def test_approval_transitions_to_done(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Approval transitions state to DONE after deck creation."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        last_call = calls[-1]
        assert last_call[1]["event"] == Event.DECK_CREATED
        assert last_call[1]["slides_deck_id"] == "deck_123"

    def test_approval_missing_state_shows_error(
        self, mock_say, mock_client, approval_body, mock_config
    ):
        """Missing state data shows STATE_MISSING error."""
        missing_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
        )

        with (
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
        ):
            StateMachine.return_value.get_state.return_value = missing_state

            handle_approval(approval_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["STATE_MISSING"]

    def test_approval_llm_error_shows_error(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """LLM error during deck generation shows error message."""
        from proposal_assistant.llm.client import LLMError
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.side_effect = LLMError(
                "API error", error_type="LLM_ERROR"
            )
            LLMClient.return_value = mock_llm

            handle_approval(approval_body, mock_say, mock_client)

        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["LLM_ERROR"]

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)

    def test_approval_slides_error_shows_error(
        self, mock_say, mock_client, approval_body, mock_config, mock_thread_state
    ):
        """Slides creation error shows SLIDES_ERROR message."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.side_effect = Exception("Slides API error")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["SLIDES_ERROR"]

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)

    def test_approval_with_user_uploaded_content_parses_it(
        self, mock_say, mock_client, approval_body, mock_config
    ):
        """Approval with user-uploaded content parses it before LLM call."""
        # State with user-uploaded raw content
        user_uploaded_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={
                "raw_content": "## Opportunity Snapshot\nAcme Corp details",
                "source": "user_uploaded",
            },
        )

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = user_uploaded_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        # Verify LLM was called with parsed content (not raw wrapper)
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert "raw_content" not in call_args
        assert "source" not in call_args
        assert "opportunity_snapshot" in call_args


class TestHandleRejection:
    """Tests for handle_rejection function."""

    def test_rejection_transitions_to_done(
        self, mock_say, mock_client, approval_body
    ):
        """Rejection transitions state to DONE."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
        ):
            handle_rejection(approval_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        state_machine.transition.assert_called_once()
        call_kwargs = state_machine.transition.call_args[1]
        assert call_kwargs["event"] == Event.REJECTED

    def test_rejection_sends_confirmation_message(
        self, mock_say, mock_client, approval_body
    ):
        """Rejection sends confirmation message."""
        with (
            patch("proposal_assistant.slack.handlers.StateMachine"),
        ):
            handle_rejection(approval_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == "Got it, no proposal deck will be created."

    def test_rejection_uses_correct_thread_ts(
        self, mock_say, mock_client, approval_body
    ):
        """Rejection uses correct thread_ts for reply."""
        with (
            patch("proposal_assistant.slack.handlers.StateMachine"),
        ):
            handle_rejection(approval_body, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706430000.000000"


class TestHandleRegenerate:
    """Tests for handle_regenerate function."""

    @pytest.fixture
    def regenerate_body(self):
        """Sample Slack action body for regenerate button."""
        return {
            "channel": {"id": "C1234567890"},
            "message": {"thread_ts": "1706430000.000000"},
            "user": {"id": "U1234567890"},
        }

    @pytest.fixture
    def mock_thread_state_for_regen(self):
        """Mock thread state with stored transcripts for regeneration."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            client_name="acme",
            analyse_folder_id="analyse_123",
            proposals_folder_id="proposals_123",
            input_transcript_content=["# Meeting transcript content"],
            deal_analysis_content={"company": "Acme"},
            deal_analysis_version=1,
        )

    def test_regenerate_sends_regenerating_message(
        self, mock_say, mock_client, regenerate_body, mock_config, mock_thread_state_for_regen
    ):
        """Regenerate sends regenerating status message with version."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_regen

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme v2"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2", "link_v2")
            DocsClient.return_value = mock_docs

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        first_call = mock_say.call_args_list[0][1]
        assert "Regenerating" in first_call["text"]
        assert "v2" in first_call["text"]

    def test_regenerate_increments_version(
        self, mock_say, mock_client, regenerate_body, mock_config, mock_thread_state_for_regen
    ):
        """Regenerate increments deal_analysis_version in state."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_regen

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2", "link_v2")
            DocsClient.return_value = mock_docs

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        first_call = state_machine.transition.call_args_list[0]
        assert first_call[1]["event"] == Event.REGENERATE_REQUESTED
        assert first_call[1]["deal_analysis_version"] == 2

    def test_regenerate_calls_llm_with_stored_transcripts(
        self, mock_say, mock_client, regenerate_body, mock_config, mock_thread_state_for_regen
    ):
        """Regenerate uses stored input_transcript_content for LLM call."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_regen

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2", "link_v2")
            DocsClient.return_value = mock_docs

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        mock_llm.generate_deal_analysis.assert_called_once()
        call_kwargs = mock_llm.generate_deal_analysis.call_args[1]
        assert call_kwargs["transcript"] == ["# Meeting transcript content"]

    def test_regenerate_creates_versioned_doc(
        self, mock_say, mock_client, regenerate_body, mock_config, mock_thread_state_for_regen
    ):
        """Regenerate creates doc with version number in title."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_regen

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2", "link_v2")
            DocsClient.return_value = mock_docs

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        mock_docs.create_document.assert_called_once()
        call_args = mock_docs.create_document.call_args[0]
        assert call_args[0] == "acme - Deal Analysis v2"
        assert call_args[1] == "analyse_123"

    def test_regenerate_missing_state_shows_error(
        self, mock_say, mock_client, regenerate_body
    ):
        """Missing transcript content shows STATE_MISSING error."""
        missing_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
        )

        with (
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
        ):
            StateMachine.return_value.get_state.return_value = missing_state

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["STATE_MISSING"]

    def test_regenerate_llm_error_shows_error(
        self, mock_say, mock_client, regenerate_body, mock_config, mock_thread_state_for_regen
    ):
        """LLM error during regenerate shows error message."""
        from proposal_assistant.llm.client import LLMError
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_for_regen

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.side_effect = LLMError("LLM failed", "LLM_ERROR")
            LLMClient.return_value = mock_llm

            from proposal_assistant.slack.handlers import handle_regenerate
            handle_regenerate(regenerate_body, mock_say, mock_client)

        assert mock_say.call_count == 2
        last_call = mock_say.call_args_list[-1][1]
        assert last_call["text"] == ERROR_MESSAGES["LLM_ERROR"]

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        assert any(call[1]["event"] == Event.FAILED for call in calls)


class TestHandleUpdatedDealAnalysis:
    """Tests for handle_updated_deal_analysis function."""

    @pytest.fixture
    def file_upload_message(self):
        """Create a Slack message payload with file upload."""
        return {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {
                    "id": "F123",
                    "name": "updated-analysis.md",
                    "url_private_download": "https://slack.com/files/...",
                }
            ],
        }

    @pytest.fixture
    def mock_thread_state_waiting(self):
        """Mock thread state in WAITING_FOR_APPROVAL."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={"company": "Acme"},
        )

    def test_ignores_message_without_files(self, mock_say, mock_client):
        """Handler returns early if no files in message."""
        message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
        }

        handle_updated_deal_analysis(message, mock_say, mock_client)

        mock_say.assert_not_called()

    def test_ignores_message_not_in_thread(self, mock_say, mock_client):
        """Handler returns early if message is not in a thread."""
        message = {
            "ts": "1706440000.000001",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [{"id": "F123", "name": "test.md"}],
        }

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.side_effect = Exception("No state")
            handle_updated_deal_analysis(message, mock_say, mock_client)

        mock_say.assert_not_called()

    def test_ignores_non_waiting_for_approval_state(
        self, mock_say, mock_client, file_upload_message
    ):
        """Handler ignores file upload if not in WAITING_FOR_APPROVAL state."""
        idle_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.IDLE,
        )

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = idle_state
            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        mock_say.assert_not_called()

    def test_ignores_non_docx_or_md_files(
        self, mock_say, mock_client, mock_thread_state_waiting
    ):
        """Handler ignores files that are not .docx or .md."""
        message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {"id": "F123", "name": "image.png", "url_private_download": "https://..."},
            ],
        }

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = mock_thread_state_waiting
            handle_updated_deal_analysis(message, mock_say, mock_client)

        mock_say.assert_not_called()

    def test_processes_md_file_in_waiting_state(
        self, mock_say, mock_client, file_upload_message, mock_config, mock_thread_state_waiting
    ):
        """Handler processes .md file when in WAITING_FOR_APPROVAL state."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_waiting

            mock_response = MagicMock()
            mock_response.read.return_value = b"# Updated Deal Analysis\n\nNew content."
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        # Should send generating message and completion message
        assert mock_say.call_count == 2
        first_call = mock_say.call_args_list[0][1]
        assert first_call["text"] == "Generating proposal deck..."

    def test_triggers_updated_deal_analysis_provided_event(
        self, mock_say, mock_client, file_upload_message, mock_config, mock_thread_state_waiting
    ):
        """Handler triggers UPDATED_DEAL_ANALYSIS_PROVIDED event."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_waiting

            mock_response = MagicMock()
            mock_response.read.return_value = b"# Content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {"content": {}}
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        first_call = calls[0]
        assert first_call[1]["event"] == Event.UPDATED_DEAL_ANALYSIS_PROVIDED

    def test_download_error_shows_error_message(
        self, mock_say, mock_client, file_upload_message, mock_config, mock_thread_state_waiting
    ):
        """Download failure shows INPUT_INVALID error."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_waiting
            urlopen.side_effect = Exception("Network error")

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_INVALID"]

    def test_transitions_to_done_after_deck_creation(
        self, mock_say, mock_client, file_upload_message, mock_config, mock_thread_state_waiting
    ):
        """Handler transitions to DONE after successful deck creation."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_waiting

            mock_response = MagicMock()
            mock_response.read.return_value = b"# Content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {"content": {}}
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        last_call = calls[-1]
        assert last_call[1]["event"] == Event.DECK_CREATED


class TestHandleCloudConsentYes:
    """Tests for handle_cloud_consent_yes function."""

    @pytest.fixture
    def cloud_consent_body(self):
        """Create a Slack action payload for cloud consent button click."""
        return {
            "channel": {"id": "C1234567890"},
            "message": {"ts": "1706440000.000001", "thread_ts": "1706430000.000000"},
            "user": {"id": "U1234567890"},
        }

    @pytest.fixture
    def mock_thread_state_with_transcript(self):
        """Mock thread state with stored transcript for cloud retry."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.ERROR,
            client_name="acme",
            analyse_folder_id="analyse_123",
            proposals_folder_id="proposals_123",
            input_transcript_content=["# Meeting transcript content"],
        )

    def test_cloud_consent_yes_missing_transcript_shows_error(
        self, mock_say, mock_client, cloud_consent_body
    ):
        """Missing transcript content shows STATE_MISSING error."""
        mock_thread_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
        )

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = mock_thread_state
            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["STATE_MISSING"]

    def test_cloud_consent_yes_sends_analyzing_message(
        self, mock_say, mock_client, cloud_consent_body, mock_config, mock_thread_state_with_transcript
    ):
        """Accepting cloud consent sends analyzing message and retries with cloud."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_with_transcript

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_123", "https://docs.google.com/doc")
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # First call should be "Analyzing..."
        first_call = mock_say.call_args_list[0][1]
        assert first_call["text"] == "Analyzing transcript..."
        assert first_call["thread_ts"] == "1706430000.000000"

    def test_cloud_consent_yes_calls_llm_with_use_cloud(
        self, mock_say, mock_client, cloud_consent_body, mock_config, mock_thread_state_with_transcript
    ):
        """Cloud consent yes calls LLM with use_cloud=True."""
        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_with_transcript

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_123", "link")
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        # Verify LLM was called with use_cloud=True
        mock_llm.generate_deal_analysis.assert_called_once()
        call_kwargs = mock_llm.generate_deal_analysis.call_args[1]
        assert call_kwargs["use_cloud"] is True

    def test_cloud_consent_yes_transitions_state(
        self, mock_say, mock_client, cloud_consent_body, mock_config, mock_thread_state_with_transcript
    ):
        """Cloud consent yes transitions state with cloud_consent_given=True."""
        from proposal_assistant.state.models import Event

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = mock_thread_state_with_transcript

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_123", "link")
            DocsClient.return_value = mock_docs

            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        calls = state_machine.transition.call_args_list
        first_call = calls[0]
        assert first_call[1]["event"] == Event.CLOUD_CONSENT_GIVEN
        assert first_call[1]["cloud_consent_given"] is True

    def test_cloud_consent_yes_gets_thread_state(
        self, mock_say, mock_client, cloud_consent_body
    ):
        """Accepting cloud consent retrieves thread state."""
        mock_thread_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
        )

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = mock_thread_state
            handle_cloud_consent_yes(cloud_consent_body, mock_say, mock_client)

        StateMachine.return_value.get_state.assert_called_once_with(
            "1706430000.000000",
            "C1234567890",
            "U1234567890",
        )

    def test_cloud_consent_yes_uses_message_ts_when_no_thread_ts(
        self, mock_say, mock_client
    ):
        """Uses message ts when thread_ts is not present."""
        body_no_thread = {
            "channel": {"id": "C1234567890"},
            "message": {"ts": "1706440000.000001"},
            "user": {"id": "U1234567890"},
        }

        mock_thread_state = ThreadState(
            thread_ts="1706440000.000001",
            channel_id="C1234567890",
            user_id="U1234567890",
        )

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = mock_thread_state
            handle_cloud_consent_yes(body_no_thread, mock_say, mock_client)

        # Should show error since no transcript content
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706440000.000001"


class TestHandleCloudConsentNo:
    """Tests for handle_cloud_consent_no function."""

    @pytest.fixture
    def cloud_consent_body(self):
        """Create a Slack action payload for cloud consent button click."""
        return {
            "channel": {"id": "C1234567890"},
            "message": {"ts": "1706440000.000001", "thread_ts": "1706430000.000000"},
            "user": {"id": "U1234567890"},
        }

    def test_cloud_consent_no_sends_cancelled_message(
        self, mock_say, mock_client, cloud_consent_body
    ):
        """Declining cloud consent sends cancellation message."""
        with patch("proposal_assistant.slack.handlers.StateMachine"):
            handle_cloud_consent_no(cloud_consent_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ":ok_hand: Got it, analysis cancelled."
        assert call_kwargs["thread_ts"] == "1706430000.000000"

    def test_cloud_consent_no_transitions_to_rejected(
        self, mock_say, mock_client, cloud_consent_body
    ):
        """Declining cloud consent transitions state to REJECTED."""
        from proposal_assistant.state.models import Event

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            handle_cloud_consent_no(cloud_consent_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        state_machine.transition.assert_called_once()
        call_kwargs = state_machine.transition.call_args[1]
        assert call_kwargs["event"] == Event.REJECTED
        assert call_kwargs["thread_ts"] == "1706430000.000000"
        assert call_kwargs["channel_id"] == "C1234567890"

    def test_cloud_consent_no_uses_message_ts_when_no_thread_ts(
        self, mock_say, mock_client
    ):
        """Uses message ts when thread_ts is not present."""
        body_no_thread = {
            "channel": {"id": "C1234567890"},
            "message": {"ts": "1706440000.000001"},
            "user": {"id": "U1234567890"},
        }

        with patch("proposal_assistant.slack.handlers.StateMachine"):
            handle_cloud_consent_no(body_no_thread, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706440000.000001"
