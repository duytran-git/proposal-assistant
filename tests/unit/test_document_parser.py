"""Unit tests for document parser utility."""

import pytest

from proposal_assistant.utils.document_parser import parse_docx, parse_markdown


class TestParseMarkdown:
    """Tests for parse_markdown function."""

    def test_parse_markdown_returns_content_unchanged(self):
        """parse_markdown returns the input content unchanged."""
        content = "# Heading\n\nSome content here."
        result = parse_markdown(content)
        assert result == content

    def test_parse_markdown_handles_empty_string(self):
        """parse_markdown handles empty string."""
        result = parse_markdown("")
        assert result == ""

    def test_parse_markdown_preserves_newlines(self):
        """parse_markdown preserves newlines and formatting."""
        content = "Line 1\n\nLine 2\n\n\nLine 3"
        result = parse_markdown(content)
        assert result == content


class TestParseDocx:
    """Tests for parse_docx function."""

    def test_parse_docx_invalid_bytes_raises_error(self):
        """parse_docx raises ValueError for invalid .docx bytes."""
        with pytest.raises(ValueError, match="Failed to parse .docx file"):
            parse_docx(b"not a valid docx file")

    def test_parse_docx_empty_bytes_raises_error(self):
        """parse_docx raises ValueError for empty bytes."""
        with pytest.raises(ValueError, match="Failed to parse .docx file"):
            parse_docx(b"")
