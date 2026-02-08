"""Unit tests for Google Drive client module."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.drive.client import SCOPES, DriveClient


@pytest.fixture
def mock_config():
    """Create a mock Config with Google credentials."""
    config = MagicMock()
    config.google_service_account_json = (
        '{"type": "service_account", "project_id": "test"}'
    )
    config.google_drive_root_folder_id = "root_folder_123"
    return config


@pytest.fixture
def drive_client(mock_config):
    """Create a DriveClient with mocked Google APIs."""
    with (
        patch("proposal_assistant.drive.client.Credentials") as mock_creds,
        patch("proposal_assistant.drive.client.build") as mock_build,
    ):
        mock_creds.from_service_account_info.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = DriveClient(mock_config)
        client._mock_service = mock_service
        yield client


class TestDriveClientInit:
    """Tests for DriveClient initialization."""

    def test_creates_credentials_from_config(self, mock_config):
        with (
            patch("proposal_assistant.drive.client.Credentials") as mock_creds,
            patch("proposal_assistant.drive.client.build"),
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            DriveClient(mock_config)

            mock_creds.from_service_account_info.assert_called_once()
            call_kwargs = mock_creds.from_service_account_info.call_args
            assert call_kwargs[0][0] == {
                "type": "service_account",
                "project_id": "test",
            }
            assert call_kwargs[1]["scopes"] == SCOPES

    def test_builds_drive_v3_service(self, mock_config):
        with (
            patch("proposal_assistant.drive.client.Credentials") as mock_creds,
            patch("proposal_assistant.drive.client.build") as mock_build,
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            DriveClient(mock_config)

            mock_build.assert_called_once_with(
                "drive",
                "v3",
                credentials=mock_creds.from_service_account_info.return_value,
            )

    def test_stores_root_folder_id(self, drive_client):
        assert drive_client._root_folder_id == "root_folder_123"


class TestFindFolder:
    """Tests for DriveClient.find_folder."""

    def test_returns_folder_id_when_found(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_files.list.return_value.execute.return_value = {
            "files": [{"id": "found_folder_456"}]
        }

        result = drive_client.find_folder("parent_123", "MyFolder")

        assert result == "found_folder_456"

    def test_returns_none_when_not_found(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_files.list.return_value.execute.return_value = {"files": []}

        result = drive_client.find_folder("parent_123", "NonExistent")

        assert result is None

    def test_queries_with_correct_filter(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_files.list.return_value.execute.return_value = {"files": []}

        drive_client.find_folder("parent_123", "TestFolder")

        call_kwargs = mock_files.list.call_args[1]
        assert "name = 'TestFolder'" in call_kwargs["q"]
        assert "'parent_123' in parents" in call_kwargs["q"]
        assert "mimeType = 'application/vnd.google-apps.folder'" in call_kwargs["q"]
        assert "trashed = false" in call_kwargs["q"]


class TestCreateFolder:
    """Tests for DriveClient.create_folder."""

    def test_returns_new_folder_id(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_files.create.return_value.execute.return_value = {"id": "new_folder_789"}

        result = drive_client.create_folder("parent_123", "NewFolder")

        assert result == "new_folder_789"

    def test_sends_correct_metadata(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_files.create.return_value.execute.return_value = {"id": "new_id"}

        drive_client.create_folder("parent_123", "NewFolder")

        call_kwargs = mock_files.create.call_args[1]
        body = call_kwargs["body"]
        assert body["name"] == "NewFolder"
        assert body["mimeType"] == "application/vnd.google-apps.folder"
        assert body["parents"] == ["parent_123"]
        assert call_kwargs["fields"] == "id"


class TestDownloadFile:
    """Tests for DriveClient.download_file."""

    def test_returns_file_bytes(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value
        mock_request = MagicMock()
        mock_files.get_media.return_value = mock_request

        content = b"file content here"

        with patch("proposal_assistant.drive.client.MediaIoBaseDownload") as mock_dl:
            mock_downloader = MagicMock()
            mock_dl.return_value = mock_downloader
            # Simulate single-chunk download
            mock_downloader.next_chunk.return_value = (None, True)

            # Write content into the buffer that gets passed to MediaIoBaseDownload
            def capture_buffer(buf, req):
                buf.write(content)
                return mock_downloader

            mock_dl.side_effect = capture_buffer

            result = drive_client.download_file("file_123")

        assert result == content

    def test_calls_get_media_with_file_id(self, drive_client):
        mock_files = drive_client._mock_service.files.return_value

        with patch("proposal_assistant.drive.client.MediaIoBaseDownload") as mock_dl:
            mock_dl.return_value.next_chunk.return_value = (None, True)
            drive_client.download_file("file_abc")

        mock_files.get_media.assert_called_once_with(fileId="file_abc")


class TestShareFile:
    """Tests for DriveClient.share_file."""

    def test_creates_permission_with_defaults(self, drive_client):
        mock_perms = drive_client._mock_service.permissions.return_value

        drive_client.share_file("file_123", "user@example.com")

        call_kwargs = mock_perms.create.call_args[1]
        assert call_kwargs["fileId"] == "file_123"
        assert call_kwargs["body"]["emailAddress"] == "user@example.com"
        assert call_kwargs["body"]["role"] == "writer"
        assert call_kwargs["body"]["type"] == "user"
        assert call_kwargs["sendNotificationEmail"] is False

    def test_respects_custom_role(self, drive_client):
        mock_perms = drive_client._mock_service.permissions.return_value

        drive_client.share_file("file_123", "user@example.com", role="reader")

        call_kwargs = mock_perms.create.call_args[1]
        assert call_kwargs["body"]["role"] == "reader"
