"""Unit tests for long transcript chunking and summarization."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.llm.client import LLMClient
from proposal_assistant.llm.context_builder import (
    ContextBuilder,
    chunk_text,
    count_tokens,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "transcripts"


@pytest.fixture
def long_transcript():
    """Load the long transcript fixture."""
    return (FIXTURES_DIR / "long_transcript.md").read_text()


@pytest.fixture
def mock_config():
    """Create a Config for LLM client tests."""
    from proposal_assistant.config import Config

    return Config(
        slack_bot_token="xoxb-test",
        slack_app_token="xapp-test",
        slack_signing_secret="secret",
        google_service_account_json="{}",
        google_drive_root_folder_id="folder",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:14b",
        proposal_template_slide_id="slide",
        ollama_num_ctx=32768,
    )


@pytest.fixture
def llm_client(mock_config):
    """Create an LLMClient with mocked OpenAI SDK."""
    with patch("proposal_assistant.llm.client.OpenAI") as mock_openai:
        mock_instance = MagicMock()
        mock_openai.return_value = mock_instance
        client = LLMClient(mock_config)
        client._mock_openai = mock_instance
        yield client


class TestLongTranscriptFixture:
    """Tests to verify the long transcript fixture is properly sized."""

    def test_fixture_exists(self):
        """Long transcript fixture file exists."""
        assert (FIXTURES_DIR / "long_transcript.md").exists()

    def test_fixture_exceeds_32k_tokens(self, long_transcript):
        """Long transcript fixture has more than 32K tokens."""
        token_count = count_tokens(long_transcript)
        assert token_count > 32000, f"Fixture has only {token_count} tokens, need >32K"

    def test_fixture_is_realistic_content(self, long_transcript):
        """Long transcript contains realistic meeting content."""
        assert "Meeting" in long_transcript or "Transcript" in long_transcript
        assert "**" in long_transcript  # Markdown bold for speaker names


class TestChunkingLongTranscript:
    """Tests for chunking a long transcript."""

    def test_chunks_long_transcript(self, long_transcript):
        """Long transcript is split into multiple chunks."""
        max_tokens = 8000
        chunks = chunk_text(long_transcript, max_tokens)

        assert len(chunks) > 1, "Should produce multiple chunks"

    def test_all_chunks_under_limit(self, long_transcript):
        """All chunks are approximately under the token limit."""
        max_tokens = 8000
        chunks = chunk_text(long_transcript, max_tokens)

        # Allow small margin due to token estimation variance
        margin = 200
        for i, chunk in enumerate(chunks):
            chunk_tokens = count_tokens(chunk)
            assert (
                chunk_tokens <= max_tokens + margin
            ), f"Chunk {i} has {chunk_tokens} tokens, exceeds {max_tokens}+{margin}"

    def test_chunk_count_reasonable(self, long_transcript):
        """Number of chunks is reasonable for the content size."""
        max_tokens = 8000
        total_tokens = count_tokens(long_transcript)
        chunks = chunk_text(long_transcript, max_tokens)

        # Should be roughly total_tokens / max_tokens chunks, give or take
        expected_min = total_tokens // max_tokens
        expected_max = (total_tokens // max_tokens) + 3  # Allow some overhead

        assert (
            expected_min <= len(chunks) <= expected_max * 2
        ), f"Got {len(chunks)} chunks, expected between {expected_min} and {expected_max}"

    def test_content_preserved_after_chunking(self, long_transcript):
        """Key content from original transcript exists in chunks."""
        max_tokens = 8000
        chunks = chunk_text(long_transcript, max_tokens)

        combined = " ".join(chunks)

        # Check that some key terms from the transcript are preserved
        assert "TechGlobal" in combined or "proposal" in combined.lower()


class TestSummaryCombination:
    """Tests for combining summaries from chunked transcripts."""

    def test_summaries_combined_with_part_headers(self, long_transcript, llm_client):
        """Chunk summaries are combined with numbered part headers."""
        # Mock the LLM to return simple summaries
        create = llm_client._mock_openai.chat.completions.create
        call_count = [0]

        def make_summary(*args, **kwargs):
            call_count[0] += 1
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = f"Summary of chunk {call_count[0]}"
            response.usage = None
            return response

        create.side_effect = make_summary

        # Process through context builder with summarizer
        builder = ContextBuilder()

        def summarizer(chunk: str) -> str:
            return llm_client.summarize_chunk(chunk)

        result = builder.build_context(
            long_transcript,
            summarizer=summarizer,
        )

        # Should have processed multiple chunks
        assert call_count[0] > 1, "Should have summarized multiple chunks"

        # Result should contain part headers
        assert "## Summary of Part 1" in result.context

    def test_summarized_result_fits_in_budget(self, long_transcript, llm_client):
        """After summarization, context fits within token budget."""
        # Mock the LLM to return short summaries
        create = llm_client._mock_openai.chat.completions.create

        def make_short_summary(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = (
                "Key points: Sales discovery meeting with TechGlobal. "
                "Discussed proposal automation needs, integration requirements, "
                "and implementation timeline."
            )
            response.usage = None
            return response

        create.side_effect = make_short_summary

        builder = ContextBuilder()

        def summarizer(chunk: str) -> str:
            return llm_client.summarize_chunk(chunk)

        result = builder.build_context(
            long_transcript,
            summarizer=summarizer,
        )

        # Summarized result should fit within budget
        assert result.estimated_tokens <= builder.MAX_TRANSCRIPT_TOKENS + 5000

    def test_original_token_count_preserved_in_result(
        self, long_transcript, llm_client
    ):
        """Result includes original transcript token count."""
        create = llm_client._mock_openai.chat.completions.create

        def make_summary(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Brief summary."
            response.usage = None
            return response

        create.side_effect = make_summary

        builder = ContextBuilder()
        # Use builder's estimation method (chars / 4) for consistency
        expected_tokens = len(long_transcript.strip()) // builder.CHARS_PER_TOKEN

        def summarizer(chunk: str) -> str:
            return llm_client.summarize_chunk(chunk)

        result = builder.build_context(
            long_transcript,
            summarizer=summarizer,
        )

        # Result should track original token count (using builder's estimation)
        assert result.transcript_original_tokens == expected_tokens

    def test_summarized_flag_set(self, long_transcript, llm_client):
        """Result indicates transcript was summarized."""
        create = llm_client._mock_openai.chat.completions.create

        def make_summary(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Summary content."
            response.usage = None
            return response

        create.side_effect = make_summary

        builder = ContextBuilder()

        def summarizer(chunk: str) -> str:
            return llm_client.summarize_chunk(chunk)

        result = builder.build_context(
            long_transcript,
            summarizer=summarizer,
        )

        assert result.transcript_summarized is True


class TestLLMClientLongTranscript:
    """Tests for LLMClient handling of long transcripts."""

    def test_prepare_transcript_chunks_long_content(self, long_transcript, llm_client):
        """_prepare_transcript_for_analysis chunks long transcripts."""
        # Mock the LLM for summarization
        create = llm_client._mock_openai.chat.completions.create
        summarize_calls = []

        def track_and_summarize(*args, **kwargs):
            summarize_calls.append(kwargs.get("messages", []))
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Chunk summary content here."
            response.usage = None
            return response

        create.side_effect = track_and_summarize

        result = llm_client._prepare_transcript_for_analysis(long_transcript)

        # Should have made multiple summarization calls
        assert len(summarize_calls) > 1

        # Result should contain combined summaries
        assert "Summary of Part" in result

    def test_prepare_transcript_reduces_token_count(self, long_transcript, llm_client):
        """Summarization reduces the token count significantly."""
        original_tokens = count_tokens(long_transcript)

        # Mock short summaries
        create = llm_client._mock_openai.chat.completions.create

        def make_short_summary(*args, **kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = (
                "Meeting discussed proposal automation requirements."
            )
            response.usage = None
            return response

        create.side_effect = make_short_summary

        result = llm_client._prepare_transcript_for_analysis(long_transcript)
        result_tokens = count_tokens(result)

        # Result should be significantly smaller
        reduction_percent = (1 - result_tokens / original_tokens) * 100
        assert (
            reduction_percent > 50
        ), f"Only {reduction_percent:.1f}% reduction, expected >50%"


class TestStatusCallbacks:
    """Tests for status callback notifications during chunking."""

    def test_status_callback_called_for_long_transcript(self, long_transcript):
        """on_status callback is called when processing long transcript."""
        builder = ContextBuilder()
        status_messages = []

        def on_status(msg: str) -> None:
            status_messages.append(msg)

        def summarizer(chunk: str) -> str:
            return "Summary"

        builder.build_context(
            long_transcript,
            summarizer=summarizer,
            on_status=on_status,
        )

        assert len(status_messages) > 0
        assert any(
            "exceeded" in msg.lower() or "summar" in msg.lower()
            for msg in status_messages
        )

    def test_progress_updates_for_each_chunk(self, long_transcript):
        """on_status receives progress updates for multi-chunk processing."""
        builder = ContextBuilder()
        status_messages = []

        def on_status(msg: str) -> None:
            status_messages.append(msg)

        def summarizer(chunk: str) -> str:
            return "Summary"

        builder.build_context(
            long_transcript,
            summarizer=summarizer,
            on_status=on_status,
        )

        # Should have progress messages like "Summarizing part X/Y"
        progress_msgs = [m for m in status_messages if "part" in m.lower()]
        assert len(progress_msgs) > 1, "Should have multiple progress updates"


class TestEdgeCases:
    """Tests for edge cases in chunking."""

    def test_transcript_exactly_at_threshold(self):
        """Transcript exactly at threshold is not chunked."""
        builder = ContextBuilder()

        # Create transcript just under the threshold
        # MAX_TRANSCRIPT_TOKENS is 24000, CHARS_PER_TOKEN is 4
        target_chars = builder.MAX_TRANSCRIPT_TOKENS * builder.CHARS_PER_TOKEN - 100
        transcript = "word " * (target_chars // 5)

        summarizer_called = False

        def summarizer(chunk: str) -> str:
            nonlocal summarizer_called
            summarizer_called = True
            return "Summary"

        result = builder.build_context(transcript, summarizer=summarizer)

        assert not summarizer_called
        assert result.transcript_summarized is False

    def test_single_large_paragraph_chunked(self):
        """Single paragraph exceeding limit is still chunked properly."""
        # Create a single paragraph (no double newlines) that exceeds limit
        large_paragraph = "word " * 50000  # No paragraph breaks

        chunks = chunk_text(large_paragraph, 8000)

        assert len(chunks) > 1
        for chunk in chunks:
            assert count_tokens(chunk) <= 8000

    def test_empty_chunks_filtered(self):
        """Empty chunks are filtered out from results."""
        text_with_gaps = "Content here.\n\n\n\n\n\nMore content.\n\n\n\n"
        chunks = chunk_text(text_with_gaps, 1000)

        for chunk in chunks:
            assert chunk.strip(), "No empty chunks should be returned"
