"""Unit tests for Google Drive permissions utilities."""

from unittest.mock import MagicMock, call, patch

import pytest

from proposal_assistant.drive.permissions import (
    share_with_channel_members,
    share_with_user,
)


@pytest.fixture
def mock_drive_client():
    """Create a mock DriveClient."""
    return MagicMock()


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack WebClient."""
    return MagicMock()


class TestShareWithUser:
    """Tests for share_with_user function."""

    def test_calls_share_file_with_writer_role(self, mock_drive_client):
        """share_with_user calls DriveClient.share_file as writer."""
        share_with_user(mock_drive_client, "file_123", "user@example.com")

        mock_drive_client.share_file.assert_called_once_with(
            "file_123", "user@example.com", role="writer"
        )

    def test_propagates_exceptions(self, mock_drive_client):
        """Exceptions from share_file are propagated."""
        mock_drive_client.share_file.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            share_with_user(mock_drive_client, "file_123", "user@example.com")


class TestShareWithChannelMembers:
    """Tests for share_with_channel_members function."""

    def test_gets_channel_members(self, mock_drive_client, mock_slack_client):
        """Function retrieves channel members from Slack."""
        mock_slack_client.conversations_members.return_value = {"members": []}

        share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        mock_slack_client.conversations_members.assert_called_once_with(
            channel="C_CHANNEL"
        )

    def test_returns_empty_list_when_no_members(
        self, mock_drive_client, mock_slack_client
    ):
        """Returns empty list when channel has no members."""
        mock_slack_client.conversations_members.return_value = {"members": []}

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        assert result == []
        mock_drive_client.share_file.assert_not_called()

    def test_looks_up_user_info_for_each_member(
        self, mock_drive_client, mock_slack_client
    ):
        """Function looks up user info to get email."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_USER1", "U_USER2"]
        }
        mock_slack_client.users_info.return_value = {
            "user": {"profile": {"email": "user@example.com"}, "is_bot": False}
        }

        share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        assert mock_slack_client.users_info.call_count == 2
        mock_slack_client.users_info.assert_any_call(user="U_USER1")
        mock_slack_client.users_info.assert_any_call(user="U_USER2")

    def test_shares_with_users_who_have_emails(
        self, mock_drive_client, mock_slack_client
    ):
        """Function shares file with users who have email addresses."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_USER1"]
        }
        mock_slack_client.users_info.return_value = {
            "user": {"profile": {"email": "alice@example.com"}, "is_bot": False}
        }

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        mock_drive_client.share_file.assert_called_once_with(
            "file_123", "alice@example.com", role="writer"
        )
        assert result == ["alice@example.com"]

    def test_skips_users_without_email(self, mock_drive_client, mock_slack_client):
        """Users without email addresses are skipped."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_NO_EMAIL"]
        }
        mock_slack_client.users_info.return_value = {
            "user": {"profile": {}, "is_bot": False}
        }

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        mock_drive_client.share_file.assert_not_called()
        assert result == []

    def test_skips_bot_users(self, mock_drive_client, mock_slack_client):
        """Bot users are skipped even if they have email."""
        mock_slack_client.conversations_members.return_value = {"members": ["U_BOT"]}
        mock_slack_client.users_info.return_value = {
            "user": {"profile": {"email": "bot@example.com"}, "is_bot": True}
        }

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        mock_drive_client.share_file.assert_not_called()
        assert result == []

    def test_continues_on_user_lookup_failure(
        self, mock_drive_client, mock_slack_client
    ):
        """Function continues processing if one user lookup fails."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_FAIL", "U_SUCCESS"]
        }

        def users_info_side_effect(user):
            if user == "U_FAIL":
                raise Exception("API error")
            return {
                "user": {"profile": {"email": "success@example.com"}, "is_bot": False}
            }

        mock_slack_client.users_info.side_effect = users_info_side_effect

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        assert result == ["success@example.com"]
        mock_drive_client.share_file.assert_called_once()

    def test_continues_on_share_failure(self, mock_drive_client, mock_slack_client):
        """Function continues if sharing fails for one user."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_USER1", "U_USER2"]
        }

        call_count = [0]

        def users_info_side_effect(user):
            call_count[0] += 1
            email = f"user{call_count[0]}@example.com"
            return {"user": {"profile": {"email": email}, "is_bot": False}}

        mock_slack_client.users_info.side_effect = users_info_side_effect

        share_calls = [0]

        def share_side_effect(file_id, email, role):
            share_calls[0] += 1
            if share_calls[0] == 1:
                raise Exception("Permission denied")

        mock_drive_client.share_file.side_effect = share_side_effect

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        # Second user should still be shared with
        assert result == ["user2@example.com"]
        assert mock_drive_client.share_file.call_count == 2

    def test_returns_all_shared_emails(self, mock_drive_client, mock_slack_client):
        """Function returns list of all successfully shared emails."""
        mock_slack_client.conversations_members.return_value = {
            "members": ["U_USER1", "U_USER2", "U_USER3"]
        }

        call_count = [0]

        def users_info_side_effect(user):
            call_count[0] += 1
            return {
                "user": {
                    "profile": {"email": f"user{call_count[0]}@example.com"},
                    "is_bot": False,
                }
            }

        mock_slack_client.users_info.side_effect = users_info_side_effect

        result = share_with_channel_members(
            mock_drive_client, "file_123", "C_CHANNEL", mock_slack_client
        )

        assert len(result) == 3
        assert "user1@example.com" in result
        assert "user2@example.com" in result
        assert "user3@example.com" in result
