"""Unit tests for parsing utilities."""

import pytest

from proposal_assistant.utils.parsing import extract_client_name


class TestExtractClientName:
    """Tests for extract_client_name function."""

    def test_valid_md_file_with_dash_extracts_name(self):
        """Standard case: extracts client name before first dash."""
        assert extract_client_name("acme-meeting-notes.md") == "acme"

    def test_extracts_only_first_segment(self):
        """Multiple dashes: only extracts before first dash."""
        assert extract_client_name("clientx-2024-01-notes.md") == "clientx"

    def test_non_md_file_returns_none(self):
        """Non-.md files should return None."""
        assert extract_client_name("client-notes.txt") is None
        assert extract_client_name("client-data.pdf") is None
        assert extract_client_name("client-file.doc") is None

    def test_uppercase_md_extension_accepted(self):
        """Case-insensitive .MD extension should work."""
        assert extract_client_name("client-notes.MD") == "client"

    def test_file_without_dash_returns_none(self):
        """Files without dashes should return None."""
        assert extract_client_name("nodash.md") is None
        assert extract_client_name("singleword.md") is None

    def test_dash_at_start_returns_none(self):
        """Empty client name (dash at start) should return None."""
        assert extract_client_name("-notes.md") is None

    def test_empty_filename_returns_none(self):
        """Empty filename should return None."""
        assert extract_client_name("") is None

    def test_only_extension_returns_none(self):
        """Just extension should return None."""
        assert extract_client_name(".md") is None

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("alpha-beta.md", "alpha"),
            ("COMPANY-project.md", "COMPANY"),
            ("test123-file.md", "test123"),
        ],
    )
    def test_various_valid_filenames(self, filename, expected):
        """Parametrized test for various valid patterns."""
        assert extract_client_name(filename) == expected
