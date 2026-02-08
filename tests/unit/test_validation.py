"""Unit tests for validation module."""

import pytest

from proposal_assistant.utils.validation import ValidationResult, validate_transcript


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result_has_no_errors(self):
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.error_type is None
        assert result.error_message is None

    def test_invalid_result_has_error_details(self):
        result = ValidationResult(
            is_valid=False,
            error_type="test_error",
            error_message="Test error message",
        )
        assert result.is_valid is False
        assert result.error_type == "test_error"
        assert result.error_message == "Test error message"

    def test_result_is_frozen(self):
        result = ValidationResult(is_valid=True)
        with pytest.raises(AttributeError):
            result.is_valid = False


class TestValidateTranscript:
    """Tests for validate_transcript function."""

    def test_valid_file_passes(self):
        result = validate_transcript("client-meeting.md", "Meeting content here.")
        assert result.is_valid is True
        assert result.error_type is None

    def test_empty_content_rejects(self):
        result = validate_transcript("client-meeting.md", "")
        assert result.is_valid is False
        assert result.error_type == "empty_content"
        assert "empty" in result.error_message.lower()

    def test_whitespace_only_content_rejects(self):
        result = validate_transcript("client-meeting.md", "   \n\t  ")
        assert result.is_valid is False
        assert result.error_type == "empty_content"

    def test_wrong_extension_rejects(self):
        result = validate_transcript("client-meeting.txt", "Valid content")
        assert result.is_valid is False
        assert result.error_type == "invalid_extension"
        assert ".md" in result.error_message

    @pytest.mark.parametrize("extension", [".txt", ".doc", ".pdf", ""])
    def test_various_invalid_extensions_reject(self, extension):
        result = validate_transcript(f"file{extension}", "Valid content")
        assert result.is_valid is False
        assert result.error_type == "invalid_extension"

    def test_case_insensitive_extension(self):
        result = validate_transcript("file.MD", "Valid content")
        assert result.is_valid is True

    def test_extension_check_before_content_check(self):
        """Wrong extension should be caught even with empty content."""
        result = validate_transcript("file.txt", "")
        assert result.error_type == "invalid_extension"
