"""Unit tests for Drive folder operations."""

from unittest.mock import MagicMock, call

import pytest

from proposal_assistant.drive.folders import (
    CLIENT_SUBFOLDERS,
    get_or_create_client_folder,
)


@pytest.fixture
def mock_drive():
    """Create a mock DriveClient."""
    drive = MagicMock()
    drive._root_folder_id = "root_123"
    return drive


class TestClientSubfolders:
    """Tests for CLIENT_SUBFOLDERS constant."""

    def test_contains_required_folder_names(self):
        assert "Meetings" in CLIENT_SUBFOLDERS
        assert "Analyse here" in CLIENT_SUBFOLDERS
        assert "Proposals" in CLIENT_SUBFOLDERS
        assert "References" in CLIENT_SUBFOLDERS

    def test_has_four_subfolders(self):
        assert len(CLIENT_SUBFOLDERS) == 4

    def test_maps_to_correct_keys(self):
        assert CLIENT_SUBFOLDERS["Meetings"] == "meetings_folder_id"
        assert CLIENT_SUBFOLDERS["Analyse here"] == "analyse_folder_id"
        assert CLIENT_SUBFOLDERS["Proposals"] == "proposals_folder_id"
        assert CLIENT_SUBFOLDERS["References"] == "references_folder_id"


class TestGetOrCreateClientFolder:
    """Tests for get_or_create_client_folder function."""

    def test_creates_all_folders_when_none_exist(self, mock_drive):
        mock_drive.find_folder.return_value = None
        folder_ids = iter(["client_1", "meet_2", "analyse_3", "prop_4", "ref_5"])
        mock_drive.create_folder.side_effect = lambda pid, name: next(folder_ids)

        result = get_or_create_client_folder(mock_drive, "Acme Corp")

        assert result["client_folder_id"] == "client_1"
        assert result["meetings_folder_id"] == "meet_2"
        assert result["analyse_folder_id"] == "analyse_3"
        assert result["proposals_folder_id"] == "prop_4"
        assert result["references_folder_id"] == "ref_5"

    def test_creates_client_folder_under_root(self, mock_drive):
        mock_drive.find_folder.return_value = None
        mock_drive.create_folder.return_value = "new_id"

        get_or_create_client_folder(mock_drive, "Acme Corp")

        mock_drive.create_folder.assert_any_call("root_123", "Acme Corp")

    def test_reuses_existing_client_folder(self, mock_drive):
        # First call finds client folder, rest find nothing
        find_results = iter(["existing_client", None, None, None, None])
        mock_drive.find_folder.side_effect = lambda pid, name: next(find_results)
        mock_drive.create_folder.return_value = "new_sub"

        result = get_or_create_client_folder(mock_drive, "Acme Corp")

        assert result["client_folder_id"] == "existing_client"
        # Should not create client folder, only 4 subfolders
        assert mock_drive.create_folder.call_count == 4

    def test_reuses_all_existing_folders(self, mock_drive):
        find_results = iter(["c_1", "m_1", "a_1", "p_1", "r_1"])
        mock_drive.find_folder.side_effect = lambda pid, name: next(find_results)

        result = get_or_create_client_folder(mock_drive, "Acme Corp")

        assert result == {
            "client_folder_id": "c_1",
            "meetings_folder_id": "m_1",
            "analyse_folder_id": "a_1",
            "proposals_folder_id": "p_1",
            "references_folder_id": "r_1",
        }
        mock_drive.create_folder.assert_not_called()

    def test_creates_subfolders_under_client_folder(self, mock_drive):
        mock_drive.find_folder.return_value = None
        mock_drive.create_folder.side_effect = lambda pid, name: f"id_{name}"

        get_or_create_client_folder(mock_drive, "Acme Corp")

        # Subfolders should be created under the client folder, not root
        subfolder_calls = mock_drive.create_folder.call_args_list[1:]
        for c in subfolder_calls:
            assert c[0][0] == "id_Acme Corp"

    def test_creates_analyse_here_subfolder(self, mock_drive):
        """Subfolder is named 'Analyse here', not 'Analyse'."""
        mock_drive.find_folder.return_value = None
        mock_drive.create_folder.return_value = "stub"

        get_or_create_client_folder(mock_drive, "Test Client")

        created_names = [c[0][1] for c in mock_drive.create_folder.call_args_list]
        assert "Analyse here" in created_names
        assert "Analyse" not in created_names

    def test_returns_all_expected_keys(self, mock_drive):
        mock_drive.find_folder.return_value = None
        mock_drive.create_folder.return_value = "stub"

        result = get_or_create_client_folder(mock_drive, "Test")

        expected_keys = {
            "client_folder_id",
            "meetings_folder_id",
            "analyse_folder_id",
            "proposals_folder_id",
            "references_folder_id",
        }
        assert set(result.keys()) == expected_keys

    def test_searches_root_for_client_folder(self, mock_drive):
        mock_drive.find_folder.return_value = None
        mock_drive.create_folder.return_value = "stub"

        get_or_create_client_folder(mock_drive, "Acme Corp")

        first_find = mock_drive.find_folder.call_args_list[0]
        assert first_find[0] == ("root_123", "Acme Corp")
