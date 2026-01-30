"""Unit tests for context builder module."""

from proposal_assistant.llm.context_builder import (
    ContextBuilder,
    chunk_text,
    count_tokens,
)


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


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_empty_string_returns_zero(self):
        """Empty string returns 0 tokens."""
        assert count_tokens("") == 0

    def test_none_like_empty_returns_zero(self):
        """Empty-ish string returns 0."""
        assert count_tokens("") == 0

    def test_single_word_returns_positive(self):
        """Single word returns at least 1 token."""
        result = count_tokens("hello")
        assert result >= 1

    def test_sentence_returns_reasonable_count(self):
        """Sentence returns reasonable token count."""
        text = "This is a test sentence with several words."
        result = count_tokens(text)
        # Should be roughly 1-1.5 tokens per word, so 8-15 tokens
        assert 5 <= result <= 20

    def test_longer_text_returns_more_tokens(self):
        """Longer text returns more tokens than shorter text."""
        short = "Hello"
        long = "Hello world this is a much longer piece of text"
        assert count_tokens(long) > count_tokens(short)

    def test_whitespace_only_returns_low_count(self):
        """Whitespace-only text returns low token count."""
        result = count_tokens("   \n\n   ")
        assert result <= 5


class TestChunkText:
    """Tests for chunk_text function."""

    def test_empty_string_returns_empty_list(self):
        """Empty string returns empty list."""
        assert chunk_text("", 100) == []

    def test_zero_max_tokens_returns_empty_list(self):
        """Zero max_tokens returns empty list."""
        assert chunk_text("Hello world", 0) == []

    def test_negative_max_tokens_returns_empty_list(self):
        """Negative max_tokens returns empty list."""
        assert chunk_text("Hello world", -10) == []

    def test_small_text_returns_single_chunk(self):
        """Text under limit returns single chunk."""
        text = "Short text"
        result = chunk_text(text, 1000)
        assert len(result) == 1
        assert result[0] == text

    def test_large_text_returns_multiple_chunks(self):
        """Text over limit returns multiple chunks."""
        # Create text that definitely exceeds small token limit
        text = " ".join(["word"] * 100)  # 100 words
        result = chunk_text(text, 10)  # Very small limit
        assert len(result) > 1

    def test_all_chunks_under_limit(self):
        """All returned chunks are under the token limit."""
        text = " ".join(["word"] * 200)
        max_tokens = 20
        result = chunk_text(text, max_tokens)

        for chunk in result:
            assert count_tokens(chunk) <= max_tokens

    def test_preserves_all_content(self):
        """Chunking preserves all words from original text."""
        text = "The quick brown fox jumps over the lazy dog"
        result = chunk_text(text, 5)

        # Rejoin and check all words present
        rejoined = " ".join(result)
        for word in text.split():
            assert word in rejoined

    def test_respects_paragraph_boundaries_when_possible(self):
        """Prefers splitting at paragraph boundaries."""
        # Create longer paragraphs that will definitely need splitting
        para1 = "First paragraph " + " ".join(["word"] * 20)
        para2 = "Second paragraph " + " ".join(["word"] * 20)
        text = f"{para1}\n\n{para2}"

        result = chunk_text(text, 1000)
        # Should fit in one chunk since under limit
        assert len(result) == 1

        # Now with smaller limit that forces splitting
        result = chunk_text(text, 15)
        # Should split into multiple chunks
        assert len(result) >= 2

    def test_handles_single_large_paragraph(self):
        """Handles paragraph that exceeds limit."""
        text = " ".join(["longword"] * 50)  # No paragraph breaks
        result = chunk_text(text, 10)

        assert len(result) > 1
        for chunk in result:
            assert count_tokens(chunk) <= 10

    def test_returns_list_type(self):
        """Returns a list."""
        result = chunk_text("Test text", 100)
        assert isinstance(result, list)


class TestAutoSummarization:
    """Tests for automatic transcript summarization in ContextBuilder."""

    def test_short_transcript_not_summarized(self):
        """Transcripts under limit are not summarized."""
        builder = ContextBuilder()
        summarizer_called = False

        def mock_summarizer(chunk: str) -> str:
            nonlocal summarizer_called
            summarizer_called = True
            return "summary"

        result = builder.build_context(
            "Short transcript",
            summarizer=mock_summarizer,
        )

        assert not summarizer_called
        assert result.transcript_summarized is False

    def test_long_transcript_triggers_summarization(self):
        """Transcripts over limit trigger auto-summarization when summarizer provided."""
        builder = ContextBuilder()
        # Create transcript that exceeds 24K tokens (chars / 4 = tokens)
        # 24K tokens * 4 chars = 96K chars, so we need more than that
        long_transcript = "word " * 30000  # ~150K chars = ~37.5K tokens

        summarizer_calls: list[str] = []

        def mock_summarizer(chunk: str) -> str:
            summarizer_calls.append(chunk)
            return f"Summary of {len(chunk)} chars"

        result = builder.build_context(
            long_transcript,
            summarizer=mock_summarizer,
        )

        assert len(summarizer_calls) > 0
        assert result.transcript_summarized is True

    def test_no_summarization_without_summarizer(self):
        """Long transcripts are truncated (not summarized) without summarizer."""
        builder = ContextBuilder()
        long_transcript = "word " * 30000

        result = builder.build_context(long_transcript)

        # Should truncate, not summarize
        assert result.transcript_summarized is False
        assert result.transcript_truncated is True

    def test_on_status_called_with_message(self):
        """on_status callback receives 'exceeded limit' message."""
        builder = ContextBuilder()
        long_transcript = "word " * 30000

        status_messages: list[str] = []

        def mock_summarizer(chunk: str) -> str:
            return "summary"

        def on_status(msg: str) -> None:
            status_messages.append(msg)

        builder.build_context(
            long_transcript,
            summarizer=mock_summarizer,
            on_status=on_status,
        )

        assert any("exceeded limit" in msg.lower() for msg in status_messages)

    def test_on_status_receives_progress_updates(self):
        """on_status receives progress updates for multi-chunk summarization."""
        builder = ContextBuilder()
        long_transcript = "word " * 30000

        status_messages: list[str] = []

        def mock_summarizer(chunk: str) -> str:
            return "summary"

        def on_status(msg: str) -> None:
            status_messages.append(msg)

        builder.build_context(
            long_transcript,
            summarizer=mock_summarizer,
            on_status=on_status,
        )

        # Should have progress messages like "Summarizing part 1/N..."
        progress_msgs = [m for m in status_messages if "part" in m.lower()]
        assert len(progress_msgs) > 0

    def test_summaries_combined_with_headers(self):
        """Chunk summaries are combined with part headers."""
        builder = ContextBuilder()
        long_transcript = "word " * 30000

        def mock_summarizer(chunk: str) -> str:
            return "This is a summary"

        result = builder.build_context(
            long_transcript,
            summarizer=mock_summarizer,
        )

        assert "## Summary of Part 1" in result.context

    def test_result_includes_transcript_summarized_flag(self):
        """ContextBuildResult includes transcript_summarized field."""
        builder = ContextBuilder()
        result = builder.build_context("Short text")

        assert hasattr(result, "transcript_summarized")
        assert result.transcript_summarized is False

    def test_summarized_transcript_fits_in_budget(self):
        """After summarization, context fits within token budget."""
        builder = ContextBuilder()
        long_transcript = "word " * 30000

        def mock_summarizer(chunk: str) -> str:
            # Return short summary
            return "Brief summary."

        result = builder.build_context(
            long_transcript,
            summarizer=mock_summarizer,
        )

        # Should now fit (not truncated after summarization)
        assert result.estimated_tokens <= builder.MAX_TRANSCRIPT_TOKENS + 1000
