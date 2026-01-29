"""Unit tests for DM (direct message) support."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.drive.permissions import (
    share_file,
    share_with_channel_members,
    share_with_user_by_id,
)


class TestShareWithUserById:
    """Tests for share_with_user_by_id function."""

    def test_shares_with_user_email(self):
        """Shares file with user's email from Slack profile."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.return_value = {
            "user": {
                "profile": {"email": "user@example.com"},
            }
        }

        result = share_with_user_by_id(drive, "file123", "U123", slack_client)

        assert result == "user@example.com"
        drive.share_file.assert_called_once_with(
            "file123", "user@example.com", role="writer"
        )

    def test_returns_none_when_no_email(self):
        """Returns None when user has no email in profile."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.return_value = {
            "user": {"profile": {}}
        }

        result = share_with_user_by_id(drive, "file123", "U123", slack_client)

        assert result is None
        drive.share_file.assert_not_called()

    def test_returns_none_on_slack_api_error(self):
        """Returns None when Slack API call fails."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.side_effect = Exception("API error")

        result = share_with_user_by_id(drive, "file123", "U123", slack_client)

        assert result is None
        drive.share_file.assert_not_called()

    def test_returns_none_on_drive_share_error(self):
        """Returns None when Drive share fails."""
        drive = MagicMock()
        drive.share_file.side_effect = Exception("Drive error")
        slack_client = MagicMock()
        slack_client.users_info.return_value = {
            "user": {"profile": {"email": "user@example.com"}}
        }

        result = share_with_user_by_id(drive, "file123", "U123", slack_client)

        assert result is None


class TestShareFile:
    """Tests for unified share_file function."""

    def test_dm_shares_only_with_user(self):
        """DM context shares only with the requesting user."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.return_value = {
            "user": {"profile": {"email": "dm_user@example.com"}}
        }

        result = share_file(
            drive=drive,
            file_id="file123",
            channel_id="D123",
            user_id="U456",
            slack_client=slack_client,
            channel_type="im",
        )

        assert result == ["dm_user@example.com"]
        # Should call users_info for the user, NOT conversations_members
        slack_client.users_info.assert_called_once_with(user="U456")
        slack_client.conversations_members.assert_not_called()

    def test_dm_returns_empty_list_on_failure(self):
        """DM context returns empty list when sharing fails."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.return_value = {"user": {"profile": {}}}

        result = share_file(
            drive=drive,
            file_id="file123",
            channel_id="D123",
            user_id="U456",
            slack_client=slack_client,
            channel_type="im",
        )

        assert result == []

    def test_channel_shares_with_all_members(self):
        """Channel context shares with all channel members."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.conversations_members.return_value = {
            "members": ["U1", "U2"]
        }
        slack_client.users_info.side_effect = [
            {"user": {"profile": {"email": "user1@example.com"}}},
            {"user": {"profile": {"email": "user2@example.com"}}},
        ]

        result = share_file(
            drive=drive,
            file_id="file123",
            channel_id="C123",
            user_id="U1",
            slack_client=slack_client,
            channel_type=None,
        )

        assert len(result) == 2
        assert "user1@example.com" in result
        assert "user2@example.com" in result
        slack_client.conversations_members.assert_called_once()

    def test_channel_type_none_defaults_to_channel(self):
        """None channel_type defaults to channel sharing behavior."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.conversations_members.return_value = {"members": ["U1"]}
        slack_client.users_info.return_value = {
            "user": {"profile": {"email": "user@example.com"}}
        }

        share_file(
            drive=drive,
            file_id="file123",
            channel_id="C123",
            user_id="U1",
            slack_client=slack_client,
            channel_type=None,
        )

        slack_client.conversations_members.assert_called_once()

    def test_dm_does_not_call_conversations_members(self):
        """DM context never calls conversations_members API."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.users_info.return_value = {
            "user": {"profile": {"email": "user@example.com"}}
        }

        share_file(
            drive=drive,
            file_id="file123",
            channel_id="D123",
            user_id="U456",
            slack_client=slack_client,
            channel_type="im",
        )

        slack_client.conversations_members.assert_not_called()


class TestShareWithChannelMembers:
    """Tests for share_with_channel_members to verify it's not used for DMs."""

    def test_skips_bot_users(self):
        """Skips bot users when sharing with channel members."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.conversations_members.return_value = {
            "members": ["U1", "B1"]
        }
        slack_client.users_info.side_effect = [
            {"user": {"profile": {"email": "human@example.com"}, "is_bot": False}},
            {"user": {"profile": {"email": "bot@example.com"}, "is_bot": True}},
        ]

        result = share_with_channel_members(drive, "file123", "C123", slack_client)

        assert result == ["human@example.com"]
        assert drive.share_file.call_count == 1

    def test_returns_empty_list_for_empty_channel(self):
        """Returns empty list when channel has no members."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.conversations_members.return_value = {"members": []}

        result = share_with_channel_members(drive, "file123", "C123", slack_client)

        assert result == []

    def test_handles_member_lookup_failure(self):
        """Continues sharing with other members when one lookup fails."""
        drive = MagicMock()
        slack_client = MagicMock()
        slack_client.conversations_members.return_value = {
            "members": ["U1", "U2", "U3"]
        }
        slack_client.users_info.side_effect = [
            {"user": {"profile": {"email": "user1@example.com"}}},
            Exception("API error"),
            {"user": {"profile": {"email": "user3@example.com"}}},
        ]

        result = share_with_channel_members(drive, "file123", "C123", slack_client)

        assert len(result) == 2
        assert "user1@example.com" in result
        assert "user3@example.com" in result


class TestDMFlowIntegration:
    """Integration-style tests for DM flow."""

    def test_dm_flow_complete(self):
        """Complete DM flow: user sends message, only user gets access."""
        drive = MagicMock()
        slack_client = MagicMock()

        # Simulate DM user lookup
        slack_client.users_info.return_value = {
            "user": {
                "id": "U123",
                "profile": {"email": "requester@company.com"},
                "is_bot": False,
            }
        }

        # Share file in DM context
        result = share_file(
            drive=drive,
            file_id="doc_abc123",
            channel_id="D999",  # DM channel ID
            user_id="U123",
            slack_client=slack_client,
            channel_type="im",
        )

        # Verify only the user was shared with
        assert result == ["requester@company.com"]
        assert slack_client.users_info.call_count == 1
        slack_client.users_info.assert_called_with(user="U123")

        # Verify no channel member lookup happened
        slack_client.conversations_members.assert_not_called()

        # Verify Drive share was called correctly
        drive.share_file.assert_called_once_with(
            "doc_abc123", "requester@company.com", role="writer"
        )

    def test_dm_no_error_on_missing_channel_members(self):
        """DM flow doesn't error even if conversations_members would fail."""
        drive = MagicMock()
        slack_client = MagicMock()

        # Set up user lookup to succeed
        slack_client.users_info.return_value = {
            "user": {"profile": {"email": "user@example.com"}}
        }

        # Make conversations_members fail (shouldn't be called for DM)
        slack_client.conversations_members.side_effect = Exception(
            "channel_not_found"
        )

        # Should succeed without error
        result = share_file(
            drive=drive,
            file_id="file123",
            channel_id="D123",
            user_id="U456",
            slack_client=slack_client,
            channel_type="im",
        )

        assert result == ["user@example.com"]
        # conversations_members should never be called for DMs
        slack_client.conversations_members.assert_not_called()
