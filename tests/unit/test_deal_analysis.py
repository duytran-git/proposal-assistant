"""Unit tests for deal_analysis document utilities."""

from proposal_assistant.docs.deal_analysis import create_versioned_document_title


class TestCreateVersionedDocumentTitle:
    """Tests for create_versioned_document_title function."""

    def test_version_one_no_suffix(self):
        """Version 1 returns title unchanged (no suffix)."""
        result = create_versioned_document_title("Acme - Deal Analysis", 1)
        assert result == "Acme - Deal Analysis"

    def test_version_two_adds_v2_suffix(self):
        """Version 2 returns title with v2 suffix."""
        result = create_versioned_document_title("Acme - Deal Analysis", 2)
        assert result == "Acme - Deal Analysis v2"

    def test_version_three_adds_v3_suffix(self):
        """Version 3 returns title with v3 suffix."""
        result = create_versioned_document_title("Acme - Deal Analysis", 3)
        assert result == "Acme - Deal Analysis v3"

    def test_version_ten_adds_v10_suffix(self):
        """Higher version numbers work correctly."""
        result = create_versioned_document_title("Client - Deal Analysis", 10)
        assert result == "Client - Deal Analysis v10"

    def test_version_zero_treated_as_version_one(self):
        """Version 0 or less returns title unchanged."""
        result = create_versioned_document_title("Test - Deal Analysis", 0)
        assert result == "Test - Deal Analysis"

    def test_negative_version_treated_as_version_one(self):
        """Negative version returns title unchanged."""
        result = create_versioned_document_title("Test - Deal Analysis", -1)
        assert result == "Test - Deal Analysis"

    def test_preserves_special_characters_in_title(self):
        """Special characters in title are preserved."""
        result = create_versioned_document_title("Company & Co. - Deal Analysis", 2)
        assert result == "Company & Co. - Deal Analysis v2"

    def test_empty_title_with_version(self):
        """Empty title with version suffix."""
        result = create_versioned_document_title("", 2)
        assert result == " v2"

    def test_title_with_existing_version_gets_new_suffix(self):
        """Title already containing version text gets new suffix added."""
        result = create_versioned_document_title("Acme - Deal Analysis v1", 2)
        assert result == "Acme - Deal Analysis v1 v2"
