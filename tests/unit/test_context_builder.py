"""Unit tests for context builder module."""

from proposal_assistant.llm.context_builder import ContextBuilder


class TestMergeTranscripts:
    """Tests for _merge_transcripts static method."""

    def test_single_string_returns_unchanged(self):
        """Single string transcript is returned as-is."""
        result = ContextBuilder._merge_transcripts("Hello world")
        assert result == "Hello world"

    def test_empty_string_returns_empty(self):
        """Empty string returns empty."""
        result = ContextBuilder._merge_transcripts("")
        assert result == ""

    def test_empty_list_returns_empty(self):
        """Empty list returns empty string."""
        result = ContextBuilder._merge_transcripts([])
        assert result == ""

    def test_single_item_list_returns_content(self):
        """Single-item list returns content without marker."""
        result = ContextBuilder._merge_transcripts(["Transcript content"])
        assert result == "Transcript content"

    def test_multiple_transcripts_adds_markers(self):
        """Multiple transcripts are merged with numbered markers."""
        result = ContextBuilder._merge_transcripts([
            "First transcript",
            "Second transcript",
        ])
        assert "--- Transcript 1 ---" in result
        assert "--- Transcript 2 ---" in result
        assert "First transcript" in result
        assert "Second transcript" in result

    def test_three_transcripts_adds_all_markers(self):
        """Three transcripts get markers 1, 2, 3."""
        result = ContextBuilder._merge_transcripts([
            "Transcript A",
            "Transcript B",
            "Transcript C",
        ])
        assert "--- Transcript 1 ---" in result
        assert "--- Transcript 2 ---" in result
        assert "--- Transcript 3 ---" in result

    def test_empty_items_in_list_are_filtered(self):
        """Empty strings in list are filtered out."""
        result = ContextBuilder._merge_transcripts([
            "Content",
            "",
            "   ",  # whitespace only
        ])
        # Only one non-empty item, so no markers
        assert result == "Content"

    def test_markers_are_on_separate_lines(self):
        """Markers are followed by newlines."""
        result = ContextBuilder._merge_transcripts([
            "First",
            "Second",
        ])
        # Check format: marker, newlines, content
        assert "--- Transcript 1 ---\n\n" in result
        assert "--- Transcript 2 ---\n\n" in result


class TestBuildContextWithMultipleTranscripts:
    """Tests for build_context with list of transcripts."""

    def test_build_context_with_single_transcript_string(self):
        """build_context works with single transcript string."""
        builder = ContextBuilder()
        result = builder.build_context("My transcript")

        assert result.transcript_included is True
        assert "My transcript" in result.context

    def test_build_context_with_list_of_one(self):
        """build_context works with single-item list."""
        builder = ContextBuilder()
        result = builder.build_context(["My transcript"])

        assert result.transcript_included is True
        assert "My transcript" in result.context

    def test_build_context_with_multiple_transcripts(self):
        """build_context merges multiple transcripts with markers."""
        builder = ContextBuilder()
        result = builder.build_context([
            "First meeting notes",
            "Second meeting notes",
        ])

        assert result.transcript_included is True
        assert "--- Transcript 1 ---" in result.context
        assert "--- Transcript 2 ---" in result.context
        assert "First meeting notes" in result.context
        assert "Second meeting notes" in result.context

    def test_build_context_preserves_section_header(self):
        """build_context includes TRANSCRIPT section header."""
        builder = ContextBuilder()
        result = builder.build_context(["Content"])

        assert "## TRANSCRIPT" in result.context

    def test_build_context_with_empty_list(self):
        """build_context handles empty list."""
        builder = ContextBuilder()
        result = builder.build_context([])

        assert result.transcript_included is False
        assert result.context == ""
