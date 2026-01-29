"""Unit tests for main module."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.config import Config


@pytest.fixture
def mock_config():
    """Create a mock Config for tests."""
    return Config(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        slack_signing_secret="test-signing-secret",
        google_service_account_json="{}",
        google_drive_root_folder_id="folder-id",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="test-model",
        proposal_template_slide_id="slide-id",
        ollama_num_ctx=32768,
    )


class TestCreateApp:
    """Tests for create_app function."""

    def test_creates_app_with_correct_config(self, mock_config):
        """create_app initializes Slack App with bot token and signing secret."""
        with (
            patch("proposal_assistant.main.get_config", return_value=mock_config),
            patch("proposal_assistant.main.App") as mock_app_cls,
        ):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            from proposal_assistant.main import create_app

            result = create_app()

            mock_app_cls.assert_called_once_with(
                token="xoxb-test-token",
                signing_secret="test-signing-secret",
            )
            assert result is mock_app

    def test_registers_analyse_message_handler(self, mock_config):
        """create_app registers a message handler for 'Analyse' command."""
        with (
            patch("proposal_assistant.main.get_config", return_value=mock_config),
            patch("proposal_assistant.main.App") as mock_app_cls,
        ):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            from proposal_assistant.main import create_app

            create_app()

            # Verify @app.message("Analyse") decorator was called
            mock_app.message.assert_called_once_with("Analyse")


class TestMain:
    """Tests for main function."""

    def test_starts_socket_mode_handler(self, mock_config):
        """main() creates and starts SocketModeHandler."""
        with (
            patch("proposal_assistant.main.get_config", return_value=mock_config),
            patch("proposal_assistant.main.App") as mock_app_cls,
            patch("proposal_assistant.main.SocketModeHandler") as mock_handler_cls,
        ):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            mock_handler = MagicMock()
            mock_handler_cls.return_value = mock_handler

            from proposal_assistant.main import main

            main()

            mock_handler_cls.assert_called_once_with(mock_app, "xapp-test-token")
            mock_handler.start.assert_called_once()
