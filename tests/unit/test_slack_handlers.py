"""Unit tests for Slack handlers module."""

from unittest.mock import MagicMock, call

import pytest

from proposal_assistant.slack.handlers import handle_analyse_command
from proposal_assistant.slack.messages import ERROR_MESSAGES


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


class TestHandleAnalyseCommand:
    """Tests for handle_analyse_command function."""

    def test_analyse_with_file_triggers_analyzing_message(
        self, mock_say, mock_client, base_message
    ):
        """Analyse command with file attachment sends 'Analyzing...' message."""
        base_message["files"] = [
            {"id": "F123", "name": "transcript.md", "url_private_download": "https://..."}
        ]

        handle_analyse_command(base_message, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == "Analyzing transcript..."
        assert call_kwargs["thread_ts"] == "1706440000.000001"

    def test_analyse_without_file_shows_error(
        self, mock_say, mock_client, base_message
    ):
        """Analyse command without file attachment shows INPUT_MISSING error."""
        # No files key in message
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
        base_message["files"] = [{"id": "F123", "name": "test.md"}]

        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706430000.000000"

    def test_uses_ts_when_not_in_thread(
        self, mock_say, mock_client, base_message
    ):
        """Handler uses message ts for replies when not in a thread."""
        base_message["files"] = [{"id": "F123", "name": "test.md"}]

        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["thread_ts"] == "1706440000.000001"

    def test_reply_includes_blocks(self, mock_say, mock_client, base_message):
        """Handler includes Block Kit blocks in reply."""
        base_message["files"] = [{"id": "F123", "name": "test.md"}]

        handle_analyse_command(base_message, mock_say, mock_client)

        call_kwargs = mock_say.call_args[1]
        assert "blocks" in call_kwargs
        assert isinstance(call_kwargs["blocks"], list)
        assert len(call_kwargs["blocks"]) > 0

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

        # Only one call (the error message), not multiple calls
        assert mock_say.call_count == 1
        # Verify it was the error message, not analyzing
        call_kwargs = mock_say.call_args[1]
        assert "INPUT_MISSING" in ERROR_MESSAGES
        assert call_kwargs["text"] == ERROR_MESSAGES["INPUT_MISSING"]
