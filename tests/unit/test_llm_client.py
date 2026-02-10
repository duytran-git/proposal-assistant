"""Unit tests for LLM agent module."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proposal_assistant.llm.agent import (
    LLMError,
    _extract_json,
    _prepare_transcript,
    _query_with_retry,
    _summarize_chunk,
    generate_deal_analysis,
    generate_proposal_content,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"


@pytest.fixture
def deal_analysis_json():
    """Load the deal analysis fixture JSON."""
    return json.loads((FIXTURES_DIR / "deal_analysis_response.json").read_text())


def _mock_query_response(text: str):
    """Create a mock async generator that yields a message with .result attribute."""

    async def mock_query(**kwargs):
        msg = MagicMock()
        msg.result = text
        yield msg

    return mock_query


def _mock_query_empty():
    """Create a mock async generator that yields a message with empty result."""

    async def mock_query(**kwargs):
        msg = MagicMock()
        msg.result = ""
        yield msg

    return mock_query


def _mock_query_error(exc):
    """Create a mock async generator that raises an exception."""

    async def mock_query(**kwargs):
        raise exc
        yield  # noqa: unreachable - needed to make this an async generator

    return mock_query


# ---------------------------------------------------------------------------
# LLMError
# ---------------------------------------------------------------------------


class TestLLMError:
    """Tests for LLMError exception."""

    def test_default_error_type(self):
        error = LLMError("something failed")
        assert error.error_type == "LLM_ERROR"
        assert str(error) == "something failed"

    def test_custom_error_type(self):
        error = LLMError("offline", error_type="LLM_OFFLINE")
        assert error.error_type == "LLM_OFFLINE"

    def test_is_exception_subclass(self):
        assert issubclass(LLMError, Exception)


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for _extract_json helper."""

    def test_parses_raw_json(self):
        text = '{"deal_analysis": {}, "missing_info": []}'
        result = _extract_json(text)
        assert result == {"deal_analysis": {}, "missing_info": []}

    def test_parses_fenced_json(self):
        text = '```json\n{"deal_analysis": {}, "missing_info": []}\n```'
        result = _extract_json(text)
        assert result == {"deal_analysis": {}, "missing_info": []}

    def test_parses_fenced_without_language_tag(self):
        text = '```\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_parses_fenced_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_raises_on_invalid_json(self):
        with pytest.raises(LLMError, match="not valid JSON") as exc_info:
            _extract_json("this is not json")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_raises_on_json_array(self):
        with pytest.raises(LLMError, match="not an object") as exc_info:
            _extract_json("[1, 2, 3]")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_raises_on_invalid_fenced_json(self):
        text = "```json\nnot valid json\n```"
        with pytest.raises(LLMError, match="not valid JSON") as exc_info:
            _extract_json(text)

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_fixture_json_parses(self, deal_analysis_json):
        raw = json.dumps(deal_analysis_json)
        result = _extract_json(raw)
        assert "deal_analysis" in result
        assert "missing_info" in result


# ---------------------------------------------------------------------------
# _query_with_retry
# ---------------------------------------------------------------------------


class TestQueryWithRetry:
    """Tests for _query_with_retry async function."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        mock_query = _mock_query_response("Hello, world!")
        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await _query_with_retry("test prompt", "system prompt")
        assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_empty_response_raises_llm_invalid(self):
        mock_query = _mock_query_empty()
        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            with pytest.raises(LLMError, match="empty response") as exc_info:
                await _query_with_retry("test", "system")
        assert exc_info.value.error_type == "LLM_INVALID"

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        call_count = 0

        async def flaky_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            msg = MagicMock()
            msg.result = "recovered"
            yield msg

        with (
            patch("proposal_assistant.llm.agent.query", side_effect=flaky_query),
            patch("proposal_assistant.llm.agent.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _query_with_retry("test", "system")

        assert result == "recovered"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def always_fail(**kwargs):
            raise RuntimeError("persistent error")
            yield  # noqa: unreachable

        with (
            patch("proposal_assistant.llm.agent.query", side_effect=always_fail),
            patch("proposal_assistant.llm.agent.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(LLMError, match="failed after 3 attempts") as exc_info,
        ):
            await _query_with_retry("test", "system")

        assert exc_info.value.error_type == "LLM_ERROR"

    @pytest.mark.asyncio
    async def test_does_not_retry_llm_error(self):
        """LLMError (invalid/empty responses) should not be retried."""
        call_count = 0

        async def invalid_response(**kwargs):
            nonlocal call_count
            call_count += 1
            msg = MagicMock()
            msg.result = ""
            yield msg

        with patch("proposal_assistant.llm.agent.query", side_effect=invalid_response):
            with pytest.raises(LLMError):
                await _query_with_retry("test", "system")

        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_backoff_sleep_durations(self):
        call_count = 0

        async def fail_twice(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("error")
            msg = MagicMock()
            msg.result = "ok"
            yield msg

        sleep_calls = []

        async def track_sleep(seconds):
            sleep_calls.append(seconds)

        with (
            patch("proposal_assistant.llm.agent.query", side_effect=fail_twice),
            patch("proposal_assistant.llm.agent.asyncio.sleep", side_effect=track_sleep),
        ):
            await _query_with_retry("test", "system")

        assert sleep_calls == [1, 2]


# ---------------------------------------------------------------------------
# generate_deal_analysis
# ---------------------------------------------------------------------------


class TestGenerateDealAnalysis:
    """Tests for generate_deal_analysis async function."""

    @pytest.mark.asyncio
    async def test_returns_content_and_missing_info(self, deal_analysis_json):
        raw_json = json.dumps(deal_analysis_json)
        mock_query = _mock_query_response(raw_json)

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await generate_deal_analysis("Meeting transcript here")

        assert isinstance(result["content"], dict)
        assert result["content"]["opportunity_snapshot"]["company"] == "Acme Corp"
        assert result["missing_info"] == [
            "Budget range",
            "Competing vendors under evaluation",
            "Contract renewal timeline for current SAP license",
        ]
        assert result["raw_response"] == raw_json

    @pytest.mark.asyncio
    async def test_handles_fenced_json_response(self, deal_analysis_json):
        fenced = f"```json\n{json.dumps(deal_analysis_json)}\n```"
        mock_query = _mock_query_response(fenced)

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await generate_deal_analysis("transcript")

        assert result["content"]["opportunity_snapshot"]["company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_empty_missing_info_defaults_to_list(self):
        data = {"deal_analysis": {"opportunity_snapshot": {}}}
        mock_query = _mock_query_response(json.dumps(data))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await generate_deal_analysis("transcript")

        assert result["missing_info"] == []

    @pytest.mark.asyncio
    async def test_invalid_json_raises_llm_invalid(self):
        mock_query = _mock_query_response("not json at all")

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            with pytest.raises(LLMError) as exc_info:
                await generate_deal_analysis("transcript")

        assert exc_info.value.error_type == "LLM_INVALID"

    @pytest.mark.asyncio
    async def test_non_dict_deal_analysis_raises_llm_invalid(self):
        data = {"deal_analysis": "just a string", "missing_info": []}
        mock_query = _mock_query_response(json.dumps(data))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            with pytest.raises(LLMError, match="not an object") as exc_info:
                await generate_deal_analysis("transcript")

        assert exc_info.value.error_type == "LLM_INVALID"

    @pytest.mark.asyncio
    async def test_non_list_missing_info_defaults_to_empty(self):
        data = {"deal_analysis": {}, "missing_info": "not a list"}
        mock_query = _mock_query_response(json.dumps(data))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await generate_deal_analysis("transcript")

        assert result["missing_info"] == []


# ---------------------------------------------------------------------------
# _summarize_chunk
# ---------------------------------------------------------------------------


class TestSummarizeChunk:
    """Tests for _summarize_chunk async function."""

    @pytest.mark.asyncio
    async def test_returns_summary_from_llm(self):
        mock_query = _mock_query_response("This is a summary of the chunk.")
        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await _summarize_chunk("Long transcript text here...")
        assert result == "This is a summary of the chunk."

    @pytest.mark.asyncio
    async def test_empty_string_returns_empty(self):
        result = await _summarize_chunk("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty(self):
        result = await _summarize_chunk("   \n\t  ")
        assert result == ""


# ---------------------------------------------------------------------------
# _prepare_transcript
# ---------------------------------------------------------------------------


class TestPrepareTranscript:
    """Tests for _prepare_transcript async function."""

    @pytest.mark.asyncio
    async def test_short_transcript_returned_unchanged(self):
        short_text = "Short transcript content"
        result = await _prepare_transcript(short_text)
        assert result == short_text

    @pytest.mark.asyncio
    async def test_empty_string_returns_empty(self):
        result = await _prepare_transcript("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_list_of_transcripts_merged(self):
        transcripts = ["First transcript", "Second transcript"]
        result = await _prepare_transcript(transcripts)
        assert "First transcript" in result
        assert "Second transcript" in result
        assert "---" in result

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        result = await _prepare_transcript([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_long_transcript_gets_chunked_and_summarized(self):
        long_text = "word " * 40000  # ~40K words ≈ 52K tokens

        mock_query = _mock_query_response("Chunk summary")
        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await _prepare_transcript(long_text)

        assert "Summary of Part" in result

    @pytest.mark.asyncio
    async def test_summaries_numbered_sequentially(self):
        long_text = "word " * 40000

        mock_query = _mock_query_response("Chunk summary content")
        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await _prepare_transcript(long_text)

        assert "## Summary of Part 1" in result


# ---------------------------------------------------------------------------
# generate_deal_analysis with long transcripts
# ---------------------------------------------------------------------------


class TestGenerateDealAnalysisWithLongTranscripts:
    """Tests for generate_deal_analysis handling of long transcripts."""

    @pytest.mark.asyncio
    async def test_long_transcript_preprocessed_before_analysis(
        self, deal_analysis_json
    ):
        long_text = "word " * 40000
        call_count = 0

        async def smart_query(**kwargs):
            nonlocal call_count
            call_count += 1
            msg = MagicMock()
            # Check the system prompt to distinguish summarization from analysis
            options = kwargs.get("options")
            system = getattr(options, "system_prompt", "") if options else ""
            if "sales advisor" in system.lower() or "deal analysis" in system.lower():
                msg.result = json.dumps(deal_analysis_json)
            else:
                msg.result = "Chunk summary content"
            yield msg

        with patch("proposal_assistant.llm.agent.query", side_effect=smart_query):
            result = await generate_deal_analysis(long_text)

        assert isinstance(result["content"], dict)
        assert call_count > 1


# ---------------------------------------------------------------------------
# generate_proposal_content
# ---------------------------------------------------------------------------


class TestGenerateProposalContent:
    """Tests for generate_proposal_content async function."""

    @pytest.mark.asyncio
    async def test_returns_slide_content(self):
        deck_response = {
            "slide_1_cover": {"title": "Proposal"},
            "slide_2_executive_summary": {"summary": "Summary text"},
            "slide_3_client_context": {"context": "Context"},
            "slide_4_challenges": {"challenges": ["Challenge 1"]},
            "slide_5_proposed_solution": {"solution": "Solution"},
            "slide_6_solution_scope": {"scope": "Scope"},
            "slide_7_implementation": {"timeline": "Timeline"},
            "slide_8_value_case": {"value": "Value"},
            "slide_9_commercials": {"pricing": "Pricing"},
            "slide_10_risk_mitigation": {"risks": ["Risk 1"]},
            "slide_11_proof_of_success": {"proof": "Proof"},
            "slide_12_next_steps": {"steps": ["Step 1"]},
        }
        mock_query = _mock_query_response(json.dumps(deck_response))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            result = await generate_proposal_content({"deal": "analysis"})

        assert result["content"]["slide_1_cover"]["title"] == "Proposal"
        assert "raw_response" in result

    @pytest.mark.asyncio
    async def test_missing_slides_logged_as_warning(self, caplog):
        partial_response = {
            "slide_1_cover": {"title": "Proposal"},
            "slide_2_executive_summary": {"summary": "Summary"},
        }
        mock_query = _mock_query_response(json.dumps(partial_response))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            import logging

            with caplog.at_level(logging.WARNING):
                await generate_proposal_content({})

        assert "missing slide keys" in caplog.text

    @pytest.mark.asyncio
    async def test_non_dict_slide_raises_llm_invalid(self):
        invalid_response = {
            "slide_1_cover": "not a dict",
            "slide_2_executive_summary": {},
            "slide_3_client_context": {},
            "slide_4_challenges": {},
            "slide_5_proposed_solution": {},
            "slide_6_solution_scope": {},
            "slide_7_implementation": {},
            "slide_8_value_case": {},
            "slide_9_commercials": {},
            "slide_10_risk_mitigation": {},
            "slide_11_proof_of_success": {},
            "slide_12_next_steps": {},
        }
        mock_query = _mock_query_response(json.dumps(invalid_response))

        with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
            with pytest.raises(LLMError, match="not an object") as exc_info:
                await generate_proposal_content({})

        assert exc_info.value.error_type == "LLM_INVALID"
