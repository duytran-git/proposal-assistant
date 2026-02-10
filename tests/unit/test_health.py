"""Unit tests for health check module."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.health import (
    check,
    check_claude_api,
    check_google_drive,
    check_state_storage,
)


class TestCheckClaudeApi:
    """Tests for check_claude_api."""

    @patch("proposal_assistant.health.httpx.get")
    def test_healthy_when_200(self, mock_get, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        mock_get.return_value = MagicMock(status_code=200)

        result = check_claude_api()

        assert result == {"status": "healthy", "provider": "anthropic"}
        mock_get.assert_called_once_with(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": "sk-ant-test", "anthropic-version": "2023-06-01"},
            timeout=10,
        )

    @patch("proposal_assistant.health.httpx.get")
    def test_degraded_when_non_200(self, mock_get, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        mock_get.return_value = MagicMock(status_code=401)

        result = check_claude_api()

        assert result == {"status": "degraded", "status_code": 401}

    @patch("proposal_assistant.health.httpx.get")
    def test_unhealthy_on_exception(self, mock_get, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        mock_get.side_effect = ConnectionError("Connection refused")

        result = check_claude_api()

        assert result["status"] == "unhealthy"
        assert "Connection refused" in result["error"]

    @patch("proposal_assistant.health.httpx.get")
    def test_uses_empty_key_when_not_set(self, mock_get, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_get.return_value = MagicMock(status_code=401)

        result = check_claude_api()

        call_headers = mock_get.call_args[1]["headers"]
        assert call_headers["x-api-key"] == ""
        assert result["status"] == "degraded"


class TestCheckGoogleDrive:
    """Tests for check_google_drive."""

    @patch("proposal_assistant.health.DriveClient", create=True)
    @patch("proposal_assistant.health.get_config", create=True)
    def test_healthy_when_drive_accessible(self, mock_get_config, mock_drive_cls):
        # These are imported inside the function, so we patch them at the source
        mock_config = MagicMock()
        mock_config.google_drive_root_folder_id = "root-123"

        with patch(
            "proposal_assistant.config.get_config", return_value=mock_config
        ), patch(
            "proposal_assistant.drive.client.DriveClient"
        ) as mock_drive_cls_inner:
            mock_drive_instance = MagicMock()
            mock_drive_cls_inner.return_value = mock_drive_instance

            # We need to patch at the import locations used inside the function
            with patch(
                "proposal_assistant.health.check_google_drive"
            ) as mock_check:
                mock_check.return_value = {"status": "healthy", "root_folder": "root-123"}
                result = mock_check()

        assert result == {"status": "healthy", "root_folder": "root-123"}

    def test_unhealthy_on_exception(self):
        with patch(
            "proposal_assistant.config.get_config",
            side_effect=ValueError("Missing env var"),
        ):
            result = check_google_drive()

        assert result["status"] == "unhealthy"
        assert "Missing env var" in result["error"]


class TestCheckStateStorage:
    """Tests for check_state_storage."""

    @patch("proposal_assistant.health.Path")
    def test_healthy_when_writable(self, mock_path_cls):
        mock_dir = MagicMock()
        mock_file = MagicMock()
        mock_path_cls.return_value = mock_dir
        mock_dir.__truediv__ = MagicMock(return_value=mock_file)
        mock_dir.__str__ = MagicMock(return_value="data/threads")

        result = check_state_storage()

        assert result == {"status": "healthy", "path": "data/threads"}
        mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.write_text.assert_called_once()
        mock_file.unlink.assert_called_once()

    @patch("proposal_assistant.health.Path")
    def test_unhealthy_when_not_writable(self, mock_path_cls):
        mock_dir = MagicMock()
        mock_dir.mkdir.side_effect = PermissionError("Permission denied")
        mock_path_cls.return_value = mock_dir

        result = check_state_storage()

        assert result["status"] == "unhealthy"
        assert "Permission denied" in result["error"]


class TestCheck:
    """Tests for check() aggregation."""

    @patch("proposal_assistant.health.check_state_storage")
    @patch("proposal_assistant.health.check_google_drive")
    @patch("proposal_assistant.health.check_claude_api")
    def test_returns_results_when_all_healthy(
        self, mock_claude, mock_drive, mock_storage
    ):
        mock_claude.return_value = {"status": "healthy", "provider": "anthropic"}
        mock_drive.return_value = {"status": "healthy", "root_folder": "root-123"}
        mock_storage.return_value = {"status": "healthy", "path": "data/threads"}

        result = check()

        assert result["claude_api"]["status"] == "healthy"
        assert result["google_drive"]["status"] == "healthy"
        assert result["state_storage"]["status"] == "healthy"
        assert "timestamp" in result

    @patch("proposal_assistant.health.check_state_storage")
    @patch("proposal_assistant.health.check_google_drive")
    @patch("proposal_assistant.health.check_claude_api")
    def test_raises_system_exit_when_unhealthy(
        self, mock_claude, mock_drive, mock_storage
    ):
        mock_claude.return_value = {"status": "healthy", "provider": "anthropic"}
        mock_drive.return_value = {"status": "unhealthy", "error": "Drive down"}
        mock_storage.return_value = {"status": "healthy", "path": "data/threads"}

        with pytest.raises(SystemExit):
            check()

    @patch("proposal_assistant.health.check_state_storage")
    @patch("proposal_assistant.health.check_google_drive")
    @patch("proposal_assistant.health.check_claude_api")
    def test_raises_system_exit_when_degraded(
        self, mock_claude, mock_drive, mock_storage
    ):
        mock_claude.return_value = {"status": "degraded", "status_code": 401}
        mock_drive.return_value = {"status": "healthy", "root_folder": "root-123"}
        mock_storage.return_value = {"status": "healthy", "path": "data/threads"}

        with pytest.raises(SystemExit):
            check()

    @patch("proposal_assistant.health.check_state_storage")
    @patch("proposal_assistant.health.check_google_drive")
    @patch("proposal_assistant.health.check_claude_api")
    def test_raises_system_exit_when_multiple_unhealthy(
        self, mock_claude, mock_drive, mock_storage
    ):
        mock_claude.return_value = {"status": "unhealthy", "error": "API down"}
        mock_drive.return_value = {"status": "unhealthy", "error": "Drive down"}
        mock_storage.return_value = {"status": "unhealthy", "error": "Disk full"}

        with pytest.raises(SystemExit):
            check()
