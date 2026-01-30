"""Unit tests for LLM client module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from proposal_assistant.config import Config
from proposal_assistant.llm.client import LLMClient, LLMError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"


@pytest.fixture
def mock_config():
    """Create a Config for LLM client tests."""
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
        client._mock_openai_cls = mock_openai
        client._mock_openai = mock_instance
        yield client


@pytest.fixture
def deal_analysis_json():
    """Load the deal analysis fixture JSON."""
    return json.loads((FIXTURES_DIR / "deal_analysis_response.json").read_text())


def _make_response(content: str | None, usage: MagicMock | None = None):
    """Build a mock OpenAI ChatCompletion response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestLLMClientInit:
    """Tests for LLMClient initialization."""

    def test_creates_openai_client_with_config(self, mock_config):
        with patch("proposal_assistant.llm.client.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            LLMClient(mock_config)

            mock_openai.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )

    def test_stores_model_and_num_ctx(self, llm_client, mock_config):
        assert llm_client._model == "qwen2.5:14b"
        assert llm_client._num_ctx == 32768


# ---------------------------------------------------------------------------
# check_ollama_health
# ---------------------------------------------------------------------------


class TestCheckOllamaHealth:
    """Tests for LLMClient.check_ollama_health."""

    def test_returns_true_on_success(self, llm_client):
        llm_client._mock_openai.models.list.return_value = MagicMock()

        result = llm_client.check_ollama_health()

        assert result is True
        llm_client._mock_openai.models.list.assert_called_once()

    def test_returns_false_on_connection_error(self, llm_client):
        llm_client._mock_openai.models.list.side_effect = APIConnectionError(
            request=httpx.Request("GET", "http://test")
        )

        result = llm_client.check_ollama_health()

        assert result is False

    def test_returns_false_on_api_error(self, llm_client):
        mock_response = httpx.Response(500, request=httpx.Request("GET", "http://test"))
        llm_client._mock_openai.models.list.side_effect = APIStatusError(
            "Server error", response=mock_response, body=None
        )

        result = llm_client.check_ollama_health()

        assert result is False

    def test_returns_false_on_unexpected_exception(self, llm_client):
        llm_client._mock_openai.models.list.side_effect = RuntimeError("unexpected")

        result = llm_client.check_ollama_health()

        assert result is False


# ---------------------------------------------------------------------------
# generate() happy path
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for LLMClient.generate."""

    def test_returns_content_on_success(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Hello, world!")

        result = llm_client.generate([{"role": "user", "content": "Hi"}])

        assert result == "Hello, world!"

    def test_passes_model_and_temperature(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("ok")

        llm_client.generate(
            [{"role": "user", "content": "test"}],
            temperature=0.7,
        )

        call_kwargs = create.call_args[1]
        assert call_kwargs["model"] == "qwen2.5:14b"
        assert call_kwargs["temperature"] == 0.7

    def test_passes_num_ctx_in_extra_body(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("ok")

        llm_client.generate([{"role": "user", "content": "test"}])

        call_kwargs = create.call_args[1]
        assert call_kwargs["extra_body"] == {"options": {"num_ctx": 32768}}

    def test_uses_default_temperature_03(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("ok")

        llm_client.generate([{"role": "user", "content": "test"}])

        call_kwargs = create.call_args[1]
        assert call_kwargs["temperature"] == 0.3


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for _call_with_retry backoff and retry behavior."""

    def test_retries_on_api_status_error(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        mock_response = httpx.Response(500, request=httpx.Request("POST", "http://test"))
        create.side_effect = [
            APIStatusError("Server error", response=mock_response, body=None),
            _make_response("recovered"),
        ]

        with patch("proposal_assistant.llm.client.time.sleep"):
            result = llm_client.generate([{"role": "user", "content": "test"}])

        assert result == "recovered"
        assert create.call_count == 2

    def test_retries_on_api_timeout_error(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        mock_request = httpx.Request("POST", "http://test")
        create.side_effect = [
            APITimeoutError(request=mock_request),
            _make_response("recovered"),
        ]

        with patch("proposal_assistant.llm.client.time.sleep"):
            result = llm_client.generate([{"role": "user", "content": "test"}])

        assert result == "recovered"

    def test_retries_on_unexpected_exception(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.side_effect = [
            RuntimeError("unexpected"),
            _make_response("ok"),
        ]

        with patch("proposal_assistant.llm.client.time.sleep"):
            result = llm_client.generate([{"role": "user", "content": "test"}])

        assert result == "ok"

    def test_backoff_sleep_durations(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        mock_response = httpx.Response(500, request=httpx.Request("POST", "http://test"))
        create.side_effect = [
            APIStatusError("err", response=mock_response, body=None),
            APIStatusError("err", response=mock_response, body=None),
            _make_response("ok"),
        ]

        with patch("proposal_assistant.llm.client.time.sleep") as mock_sleep:
            llm_client.generate([{"role": "user", "content": "test"}])

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_raises_llm_error_after_max_retries(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        mock_response = httpx.Response(500, request=httpx.Request("POST", "http://test"))
        create.side_effect = APIStatusError(
            "Server error", response=mock_response, body=None
        )

        with (
            patch("proposal_assistant.llm.client.time.sleep"),
            pytest.raises(LLMError, match="failed after 3 attempts") as exc_info,
        ):
            llm_client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.error_type == "LLM_ERROR"
        assert create.call_count == 3


# ---------------------------------------------------------------------------
# Error cases (no retry)
# ---------------------------------------------------------------------------


class TestNoRetryErrors:
    """Tests for errors that should NOT be retried."""

    def test_empty_response_raises_llm_invalid(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("")

        with pytest.raises(LLMError, match="empty response") as exc_info:
            llm_client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.error_type == "LLM_INVALID"
        assert create.call_count == 1  # No retry

    def test_whitespace_only_response_raises_llm_invalid(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("   \n  ")

        with pytest.raises(LLMError, match="empty response") as exc_info:
            llm_client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.error_type == "LLM_INVALID"
        assert create.call_count == 1

    def test_none_content_raises_llm_invalid(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(None)

        with pytest.raises(LLMError, match="empty response"):
            llm_client.generate([{"role": "user", "content": "test"}])

        assert create.call_count == 1


# ---------------------------------------------------------------------------
# Connection errors → LLM_OFFLINE
# ---------------------------------------------------------------------------


class TestConnectionErrors:
    """Tests for APIConnectionError → LLM_OFFLINE."""

    def test_connection_error_raises_llm_offline(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.side_effect = APIConnectionError(request=httpx.Request("POST", "http://test"))

        with (
            patch("proposal_assistant.llm.client.time.sleep"),
            pytest.raises(LLMError, match="Cannot connect") as exc_info,
        ):
            llm_client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.error_type == "LLM_OFFLINE"
        assert create.call_count == 3

    def test_connection_error_retries_before_failing(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.side_effect = [
            APIConnectionError(request=httpx.Request("POST", "http://test")),
            _make_response("connected!"),
        ]

        with patch("proposal_assistant.llm.client.time.sleep"):
            result = llm_client.generate([{"role": "user", "content": "test"}])

        assert result == "connected!"


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for LLMClient._extract_json."""

    def test_parses_raw_json(self):
        text = '{"deal_analysis": {}, "missing_info": []}'
        result = LLMClient._extract_json(text)
        assert result == {"deal_analysis": {}, "missing_info": []}

    def test_parses_fenced_json(self):
        text = '```json\n{"deal_analysis": {}, "missing_info": []}\n```'
        result = LLMClient._extract_json(text)
        assert result == {"deal_analysis": {}, "missing_info": []}

    def test_parses_fenced_without_language_tag(self):
        text = '```\n{"key": "value"}\n```'
        result = LLMClient._extract_json(text)
        assert result == {"key": "value"}

    def test_parses_fenced_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = LLMClient._extract_json(text)
        assert result == {"key": "value"}

    def test_raises_on_invalid_json(self):
        with pytest.raises(LLMError, match="not valid JSON") as exc_info:
            LLMClient._extract_json("this is not json")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_raises_on_json_array(self):
        with pytest.raises(LLMError, match="not an object") as exc_info:
            LLMClient._extract_json("[1, 2, 3]")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_raises_on_invalid_fenced_json(self):
        text = '```json\nnot valid json\n```'
        with pytest.raises(LLMError, match="not valid JSON") as exc_info:
            LLMClient._extract_json(text)

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_fixture_json_parses(self, deal_analysis_json):
        raw = json.dumps(deal_analysis_json)
        result = LLMClient._extract_json(raw)
        assert "deal_analysis" in result
        assert "missing_info" in result


# ---------------------------------------------------------------------------
# generate_deal_analysis
# ---------------------------------------------------------------------------


class TestGenerateDealAnalysis:
    """Tests for LLMClient.generate_deal_analysis."""

    def test_returns_content_and_missing_info(self, llm_client, deal_analysis_json):
        raw_json = json.dumps(deal_analysis_json)
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(raw_json)

        result = llm_client.generate_deal_analysis("Meeting transcript here")

        assert isinstance(result["content"], dict)
        assert result["content"]["opportunity_snapshot"]["company"] == "Acme Corp"
        assert result["missing_info"] == [
            "Budget range",
            "Competing vendors under evaluation",
            "Contract renewal timeline for current SAP license",
        ]
        assert result["raw_response"] == raw_json

    def test_sends_system_and_user_messages(self, llm_client, deal_analysis_json):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(deal_analysis_json))

        llm_client.generate_deal_analysis("transcript text")

        messages = create.call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert "senior sales advisor" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "transcript text" in messages[1]["content"]

    def test_passes_references_to_context(self, llm_client, deal_analysis_json):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(deal_analysis_json))

        llm_client.generate_deal_analysis(
            "transcript",
            references=["ref doc 1", "ref doc 2"],
        )

        messages = create.call_args[1]["messages"]
        user_content = messages[1]["content"]
        assert "ref doc 1" in user_content
        assert "ref doc 2" in user_content

    def test_passes_web_content_to_context(self, llm_client, deal_analysis_json):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(deal_analysis_json))

        llm_client.generate_deal_analysis(
            "transcript",
            web_content=["web page content"],
        )

        messages = create.call_args[1]["messages"]
        user_content = messages[1]["content"]
        assert "web page content" in user_content

    def test_handles_fenced_json_response(self, llm_client, deal_analysis_json):
        fenced = f"```json\n{json.dumps(deal_analysis_json)}\n```"
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(fenced)

        result = llm_client.generate_deal_analysis("transcript")

        assert result["content"]["opportunity_snapshot"]["company"] == "Acme Corp"

    def test_empty_missing_info_defaults_to_list(self, llm_client):
        data = {"deal_analysis": {"opportunity_snapshot": {}}}
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(data))

        result = llm_client.generate_deal_analysis("transcript")

        assert result["missing_info"] == []

    def test_invalid_json_raises_llm_invalid(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("not json at all")

        with pytest.raises(LLMError) as exc_info:
            llm_client.generate_deal_analysis("transcript")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_non_dict_deal_analysis_raises_llm_invalid(self, llm_client):
        data = {"deal_analysis": "just a string", "missing_info": []}
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(data))

        with pytest.raises(LLMError, match="not an object") as exc_info:
            llm_client.generate_deal_analysis("transcript")

        assert exc_info.value.error_type == "LLM_INVALID"

    def test_non_list_missing_info_defaults_to_empty(self, llm_client):
        data = {"deal_analysis": {}, "missing_info": "not a list"}
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response(json.dumps(data))

        result = llm_client.generate_deal_analysis("transcript")

        assert result["missing_info"] == []


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
# Usage logging
# ---------------------------------------------------------------------------


class TestUsageLogging:
    """Tests for _log_usage."""

    def test_logs_with_usage(self, llm_client, caplog):
        usage = MagicMock()
        usage.prompt_tokens = 100
        usage.completion_tokens = 50

        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("ok", usage=usage)

        with caplog.at_level("INFO"):
            llm_client.generate([{"role": "user", "content": "test"}])

        assert "prompt=100" in caplog.text
        assert "completion=50" in caplog.text

    def test_logs_without_usage(self, llm_client, caplog):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("ok", usage=None)

        with caplog.at_level("INFO"):
            llm_client.generate([{"role": "user", "content": "test"}])

        assert "usage not reported" in caplog.text


# ---------------------------------------------------------------------------
# summarize_chunk
# ---------------------------------------------------------------------------


class TestSummarizeChunk:
    """Tests for LLMClient.summarize_chunk."""

    def test_returns_summary_from_llm(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("This is a summary of the chunk.")

        result = llm_client.summarize_chunk("Long transcript text here...")

        assert result == "This is a summary of the chunk."

    def test_uses_summarize_system_prompt(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Summary")

        llm_client.summarize_chunk("chunk text")

        messages = create.call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert "summarizer" in messages[0]["content"]

    def test_includes_chunk_in_user_message(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Summary")

        llm_client.summarize_chunk("my chunk content here")

        messages = create.call_args[1]["messages"]
        assert messages[1]["role"] == "user"
        assert "my chunk content here" in messages[1]["content"]

    def test_empty_string_returns_empty(self, llm_client):
        result = llm_client.summarize_chunk("")
        assert result == ""

    def test_whitespace_only_returns_empty(self, llm_client):
        result = llm_client.summarize_chunk("   \n\t  ")
        assert result == ""

    def test_uses_low_temperature(self, llm_client):
        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Summary")

        llm_client.summarize_chunk("chunk")

        call_kwargs = create.call_args[1]
        assert call_kwargs["temperature"] == 0.2


# ---------------------------------------------------------------------------
# _prepare_transcript_for_analysis
# ---------------------------------------------------------------------------


class TestPrepareTranscriptForAnalysis:
    """Tests for LLMClient._prepare_transcript_for_analysis."""

    def test_short_transcript_returned_unchanged(self, llm_client):
        """Transcripts under threshold are returned as-is."""
        short_text = "Short transcript content"

        result = llm_client._prepare_transcript_for_analysis(short_text)

        assert result == short_text

    def test_empty_string_returns_empty(self, llm_client):
        result = llm_client._prepare_transcript_for_analysis("")
        assert result == ""

    def test_list_of_transcripts_merged(self, llm_client):
        """Multiple transcripts are merged with separators."""
        transcripts = ["First transcript", "Second transcript"]

        result = llm_client._prepare_transcript_for_analysis(transcripts)

        assert "First transcript" in result
        assert "Second transcript" in result
        assert "---" in result

    def test_empty_list_returns_empty(self, llm_client):
        result = llm_client._prepare_transcript_for_analysis([])
        assert result == ""

    def test_long_transcript_gets_chunked_and_summarized(self, llm_client):
        """Transcripts over threshold are chunked and summarized."""
        # Create transcript that exceeds 32K tokens (roughly 4 chars per token)
        # 32K tokens ≈ 128K chars, but we'll mock to test the logic
        long_text = "word " * 40000  # ~40K words ≈ 52K tokens

        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Chunk summary")

        result = llm_client._prepare_transcript_for_analysis(long_text)

        # Should have called LLM multiple times for chunk summaries
        assert create.call_count > 0
        # Result should contain summaries
        assert "Summary of Part" in result

    def test_summaries_numbered_sequentially(self, llm_client):
        """Each chunk summary is numbered (Part 1, Part 2, etc.)."""
        long_text = "word " * 40000

        create = llm_client._mock_openai.chat.completions.create
        create.return_value = _make_response("Chunk summary content")

        result = llm_client._prepare_transcript_for_analysis(long_text)

        assert "## Summary of Part 1" in result
        # Depending on chunk count, may have more parts

    def test_uses_cloud_when_specified(self, llm_client):
        """use_cloud flag is passed to summarize_chunk calls."""
        long_text = "word " * 40000

        # Set up cloud client
        llm_client._cloud_provider = "openai"
        llm_client._cloud_client = MagicMock()
        llm_client._cloud_model = "gpt-4o"

        cloud_response = MagicMock()
        cloud_response.choices = [MagicMock()]
        cloud_response.choices[0].message.content = "Cloud summary"
        llm_client._cloud_client.chat.completions.create.return_value = cloud_response

        result = llm_client._prepare_transcript_for_analysis(
            long_text, use_cloud=True
        )

        # Should have used cloud client
        assert llm_client._cloud_client.chat.completions.create.called
        assert "Summary of Part" in result


# ---------------------------------------------------------------------------
# generate_deal_analysis with long transcripts
# ---------------------------------------------------------------------------


class TestGenerateDealAnalysisWithLongTranscripts:
    """Tests for generate_deal_analysis handling of long transcripts."""

    def test_long_transcript_preprocessed_before_analysis(
        self, llm_client, deal_analysis_json
    ):
        """Long transcripts are summarized before deal analysis generation."""
        long_text = "word " * 40000

        create = llm_client._mock_openai.chat.completions.create

        # First calls are for chunk summarization, last is for deal analysis
        def side_effect(*args, **kwargs):
            messages = kwargs.get("messages", [])
            if messages and "senior sales advisor" in messages[0].get("content", ""):
                # This is the deal analysis call
                return _make_response(json.dumps(deal_analysis_json))
            else:
                # This is a chunk summarization call
                return _make_response("Chunk summary content")

        create.side_effect = side_effect

        result = llm_client.generate_deal_analysis(long_text)

        # Should return valid deal analysis
        assert isinstance(result["content"], dict)
        # Should have made multiple calls (summarization + analysis)
        assert create.call_count > 1
