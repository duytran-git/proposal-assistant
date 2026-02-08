"""Unit tests for Slack messages module."""

import pytest

from proposal_assistant.slack.messages import (
    DEFAULT_ERROR_MESSAGE,
    ERROR_MESSAGES,
    format_analyzing,
    format_approval_buttons,
    format_cloud_consent,
    format_deal_analysis_complete,
    format_error,
    format_fetch_failures,
)


class TestFormatAnalyzing:
    """Tests for format_analyzing function."""

    def test_returns_dict_with_text_and_blocks(self):
        result = format_analyzing()
        assert isinstance(result, dict)
        assert "text" in result
        assert "blocks" in result

    def test_text_fallback_is_set(self):
        result = format_analyzing()
        assert result["text"] == "Analyzing transcript..."

    def test_blocks_contain_section(self):
        result = format_analyzing()
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["type"] == "section"

    def test_uses_mrkdwn_format(self):
        result = format_analyzing()
        text_block = result["blocks"][0]["text"]
        assert text_block["type"] == "mrkdwn"
        assert "Analyzing transcript" in text_block["text"]


class TestFormatDealAnalysisComplete:
    """Tests for format_deal_analysis_complete function."""

    def test_returns_dict_with_text_and_blocks(self):
        result = format_deal_analysis_complete("https://docs.google.com/doc/123", [])
        assert isinstance(result, dict)
        assert "text" in result
        assert "blocks" in result

    def test_includes_clickable_link(self):
        link = "https://docs.google.com/document/d/abc123"
        result = format_deal_analysis_complete(link, [])
        blocks_text = str(result["blocks"])
        assert link in blocks_text
        assert "View Deal Analysis" in blocks_text

    def test_no_missing_items_section_when_empty(self):
        result = format_deal_analysis_complete("https://example.com", [])
        blocks_text = str(result["blocks"])
        assert "Missing information" not in blocks_text

    def test_includes_missing_items_as_bullets(self):
        missing = ["Budget range", "Decision timeline"]
        result = format_deal_analysis_complete("https://example.com", missing)
        blocks_text = str(result["blocks"])
        assert "Missing information" in blocks_text
        assert "• Budget range" in blocks_text
        assert "• Decision timeline" in blocks_text

    def test_includes_continuation_prompt(self):
        result = format_deal_analysis_complete("https://example.com", [])
        blocks_text = str(result["blocks"])
        assert "Should I continue" in blocks_text

    def test_minimum_blocks_without_missing_items(self):
        result = format_deal_analysis_complete("https://example.com", [])
        # Header, link, and continuation prompt = 3 blocks minimum
        assert len(result["blocks"]) == 3

    def test_extra_block_with_missing_items(self):
        result = format_deal_analysis_complete("https://example.com", ["Item 1"])
        # Header, link, missing items, and continuation prompt = 4 blocks
        assert len(result["blocks"]) == 4


class TestFormatApprovalButtons:
    """Tests for format_approval_buttons function."""

    def test_returns_actions_block(self):
        result = format_approval_buttons()
        assert result["type"] == "actions"

    def test_has_block_id(self):
        result = format_approval_buttons()
        assert result["block_id"] == "approval_actions"

    def test_contains_two_buttons(self):
        result = format_approval_buttons()
        assert len(result["elements"]) == 2

    def test_yes_button_properties(self):
        result = format_approval_buttons()
        yes_button = result["elements"][0]
        assert yes_button["type"] == "button"
        assert yes_button["text"]["text"] == "Yes"
        assert yes_button["style"] == "primary"
        assert yes_button["action_id"] == "approve_deck"

    def test_no_button_properties(self):
        result = format_approval_buttons()
        no_button = result["elements"][1]
        assert no_button["type"] == "button"
        assert no_button["text"]["text"] == "No"
        assert no_button["style"] == "danger"
        assert no_button["action_id"] == "reject_deck"


class TestFormatCloudConsent:
    """Tests for format_cloud_consent function."""

    def test_returns_dict_with_text_and_blocks(self):
        result = format_cloud_consent()
        assert isinstance(result, dict)
        assert "text" in result
        assert "blocks" in result

    def test_text_fallback_is_set(self):
        result = format_cloud_consent()
        assert result["text"] == "Local AI unavailable. Use cloud?"

    def test_contains_two_blocks(self):
        result = format_cloud_consent()
        assert len(result["blocks"]) == 2

    def test_first_block_is_section_with_warning(self):
        result = format_cloud_consent()
        section_block = result["blocks"][0]
        assert section_block["type"] == "section"
        assert section_block["text"]["type"] == "mrkdwn"
        assert ":warning:" in section_block["text"]["text"]
        assert "Local AI unavailable" in section_block["text"]["text"]

    def test_second_block_is_actions(self):
        result = format_cloud_consent()
        actions_block = result["blocks"][1]
        assert actions_block["type"] == "actions"
        assert actions_block["block_id"] == "cloud_consent_actions"

    def test_contains_two_buttons(self):
        result = format_cloud_consent()
        elements = result["blocks"][1]["elements"]
        assert len(elements) == 2

    def test_yes_button_properties(self):
        result = format_cloud_consent()
        yes_button = result["blocks"][1]["elements"][0]
        assert yes_button["type"] == "button"
        assert yes_button["text"]["text"] == "Yes"
        assert yes_button["style"] == "primary"
        assert yes_button["action_id"] == "cloud_consent_yes"

    def test_no_button_properties(self):
        result = format_cloud_consent()
        no_button = result["blocks"][1]["elements"][1]
        assert no_button["type"] == "button"
        assert no_button["text"]["text"] == "No"
        assert no_button["style"] == "danger"
        assert no_button["action_id"] == "cloud_consent_no"


class TestFormatError:
    """Tests for format_error function."""

    def test_returns_dict_with_text_and_blocks(self):
        result = format_error("INPUT_MISSING")
        assert isinstance(result, dict)
        assert "text" in result
        assert "blocks" in result

    @pytest.mark.parametrize(
        "error_type,expected_message",
        [
            ("INPUT_MISSING", "Please attach a meeting transcript (.md file)"),
            ("INPUT_INVALID", "Transcript file appears empty or invalid"),
            ("LANGUAGE_UNSUPPORTED", "Only English transcripts supported"),
            ("DRIVE_PERMISSION", "Unable to access client folder"),
            ("DRIVE_QUOTA", "Drive temporarily unavailable"),
            ("DOCS_ERROR", "Failed to create Deal Analysis"),
            ("SLIDES_ERROR", "Failed to create proposal deck"),
            ("LLM_ERROR", "AI service temporarily unavailable"),
            ("LLM_INVALID", "Unable to generate analysis"),
            ("LLM_OFFLINE", "Local AI unavailable. Use cloud?"),
            ("APPROVAL_UNCLEAR", "Please reply 'Yes' or 'No'"),
            ("STATE_MISSING", "Lost track. Please start over"),
        ],
    )
    def test_known_error_types(self, error_type, expected_message):
        result = format_error(error_type)
        assert result["text"] == expected_message
        assert expected_message in result["blocks"][0]["text"]["text"]

    def test_unknown_error_type_returns_default(self):
        result = format_error("UNKNOWN_ERROR")
        assert result["text"] == DEFAULT_ERROR_MESSAGE

    def test_empty_error_type_returns_default(self):
        result = format_error("")
        assert result["text"] == DEFAULT_ERROR_MESSAGE

    def test_uses_mrkdwn_format(self):
        result = format_error("INPUT_MISSING")
        text_block = result["blocks"][0]["text"]
        assert text_block["type"] == "mrkdwn"


class TestErrorMessagesConstant:
    """Tests for ERROR_MESSAGES constant."""

    def test_contains_all_documented_error_types(self):
        expected_types = {
            "INPUT_MISSING",
            "INPUT_INVALID",
            "LANGUAGE_UNSUPPORTED",
            "DRIVE_PERMISSION",
            "DRIVE_QUOTA",
            "DOCS_ERROR",
            "SLIDES_ERROR",
            "LLM_ERROR",
            "LLM_INVALID",
            "LLM_OFFLINE",
            "APPROVAL_UNCLEAR",
            "STATE_MISSING",
        }
        assert set(ERROR_MESSAGES.keys()) == expected_types

    def test_all_messages_are_non_empty_strings(self):
        for error_type, message in ERROR_MESSAGES.items():
            assert isinstance(message, str), f"{error_type} message is not a string"
            assert len(message) > 0, f"{error_type} has empty message"


class TestFormatFetchFailures:
    """Tests for format_fetch_failures function."""

    def test_returns_dict_with_text_and_blocks(self):
        result = format_fetch_failures(["https://example.com"])
        assert isinstance(result, dict)
        assert "text" in result
        assert "blocks" in result

    def test_single_url_in_message(self):
        result = format_fetch_failures(["https://example.com/page"])
        assert result["text"] == "Could not fetch: https://example.com/page"
        assert "https://example.com/page" in result["blocks"][0]["text"]["text"]

    def test_multiple_urls_comma_separated(self):
        urls = ["https://a.com", "https://b.com"]
        result = format_fetch_failures(urls)
        assert result["text"] == "Could not fetch: https://a.com, https://b.com"

    def test_uses_warning_emoji(self):
        result = format_fetch_failures(["https://example.com"])
        assert ":warning:" in result["blocks"][0]["text"]["text"]

    def test_uses_mrkdwn_format(self):
        result = format_fetch_failures(["https://example.com"])
        text_block = result["blocks"][0]["text"]
        assert text_block["type"] == "mrkdwn"
