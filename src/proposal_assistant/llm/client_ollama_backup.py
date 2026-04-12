"""LLM client for Proposal Assistant using Anthropic SDK."""

import json
import logging
import re
import time
from typing import Any

import anthropic
import httpx

from proposal_assistant.config import Config
from proposal_assistant.llm.context_builder import (
    ContextBuilder,
    chunk_text,
    count_tokens,
)
from proposal_assistant.llm.prompts.deal_analysis import (
    SYSTEM_PROMPT,
    format_user_prompt,
)
from proposal_assistant.llm.prompts.proposal_deck import (
    SYSTEM_PROMPT as PROPOSAL_DECK_SYSTEM_PROMPT,
    format_user_prompt as format_proposal_deck_prompt,
)

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when an LLM operation fails.

    Attributes:
        error_type: Error code matching the error handling matrix
            (LLM_ERROR, LLM_INVALID, LLM_OFFLINE).
    """

    def __init__(self, message: str, error_type: str = "LLM_ERROR") -> None:
        self.error_type = error_type
        super().__init__(message)


SUMMARIZE_CHUNK_SYSTEM_PROMPT = """You are a meeting transcript summarizer. Your task is to create a concise but comprehensive summary of the transcript chunk provided.

Focus on capturing:
- Key discussion topics and decisions made
- Action items and who is responsible
- Important business details (companies, products, pricing, timelines)
- Problems or challenges discussed
- Proposed solutions or next steps

Write the summary in clear, professional prose. Preserve specific names, numbers, dates, and technical terms exactly as mentioned. Do not add information not present in the transcript."""

SUMMARIZE_CHUNK_USER_PROMPT = """Summarize the following transcript chunk:

{chunk}

Provide a comprehensive summary that captures all important information."""


class LLMClient:
    """LLM API client using the Anthropic SDK.

    Uses the anthropic Python SDK to call Claude as the primary LLM backend.
    Implements retry with exponential backoff for transient failures.

    Attributes:
        MAX_RETRIES: Maximum number of retry attempts.
        BACKOFF_SECONDS: Sleep durations between retries.
        CHUNK_SUMMARIZE_THRESHOLD: Token count above which transcripts are chunked.
        CHUNK_SIZE_TOKENS: Target size for each chunk when splitting.
    """

    MAX_RETRIES: int = 3
    BACKOFF_SECONDS: list[int] = [1, 2, 4]
    CHUNK_SUMMARIZE_THRESHOLD: int = 32_000
    CHUNK_SIZE_TOKENS: int = 8_000

    def __init__(self, config: Config) -> None:
        """Initialize the LLM client.

        Args:
            config: Application configuration with Anthropic API details.
        """
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self._model = config.anthropic_model

    @property
    def cloud_available(self) -> bool:
        """Check if cloud provider is configured and available.

        Always returns True since Claude IS the cloud backend.
        Kept for handler compatibility.
        """
        return True

    def check_ollama_health(self) -> bool:
        """Check if Claude API is reachable.

        Method name kept for handler compatibility.

        Returns:
            True if Claude API responds successfully, False otherwise.
        """
        try:
            resp = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": self._client.api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            healthy = resp.status_code == 200
            if healthy:
                logger.debug("Claude API health check passed")
            else:
                logger.warning("Claude API health check returned status %d", resp.status_code)
            return healthy
        except Exception as e:
            logger.warning("Claude API health check failed: %s", e)
            return False

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        use_cloud: bool = False,
    ) -> str:
        """Generate a completion from the LLM.

        Args:
            messages: Chat messages in OpenAI format
                (list of {"role": ..., "content": ...}).
            temperature: Sampling temperature (default: 0.3).
            use_cloud: Ignored. Kept for handler compatibility.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If all retries are exhausted or response is invalid.
        """
        return self._call_with_retry(messages, temperature=temperature)

    def generate_deal_analysis(
        self,
        transcript: str | list[str],
        references: list[str] | None = None,
        web_content: list[str] | None = None,
        use_cloud: bool = False,
    ) -> dict[str, Any]:
        """Generate a Deal Analysis from transcript and supporting materials.

        Assembles context within token limits, sends to LLM with the
        deal analysis prompt, and parses the structured JSON response.

        For transcripts exceeding 32K tokens, the transcript is first chunked
        and summarized before analysis to fit within context limits.

        Args:
            transcript: Meeting transcript text, or list of transcript texts.
            references: Optional reference document texts.
            web_content: Optional web research content texts.
            use_cloud: Ignored. Kept for handler compatibility.

        Returns:
            Dict with keys:
                - content: Parsed deal_analysis object (dict).
                - missing_info: List of missing information labels.
                - raw_response: Original LLM response string.

        Raises:
            LLMError: If LLM call fails or response is not valid JSON.
        """
        # Prepare transcript (chunk and summarize if >32K tokens)
        prepared_transcript = self._prepare_transcript_for_analysis(transcript)

        builder = ContextBuilder()
        result = builder.build_context(
            transcript=prepared_transcript,
            references=references,
            web_content=web_content,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": format_user_prompt(result.context)},
        ]

        raw = self.generate(messages)
        parsed = self._extract_json(raw)

        content = parsed.get("deal_analysis", {})
        missing_info = parsed.get("missing_info", [])

        if not isinstance(content, dict):
            raise LLMError(
                "deal_analysis field is not an object",
                error_type="LLM_INVALID",
            )
        if not isinstance(missing_info, list):
            missing_info = []

        logger.info(
            "Deal analysis generated (%d missing items)",
            len(missing_info),
        )

        return {
            "content": content,
            "missing_info": missing_info,
            "raw_response": raw,
        }

    def generate_proposal_deck_content(
        self,
        deal_analysis: dict[str, Any],
        use_cloud: bool = False,
    ) -> dict[str, Any]:
        """Generate Proposal Deck slide content from Deal Analysis.

        Transforms a Deal Analysis document into structured content
        for a 12-slide Proposal Deck.

        Args:
            deal_analysis: Parsed deal_analysis dict from generate_deal_analysis().
            use_cloud: Ignored. Kept for handler compatibility.

        Returns:
            Dict with keys:
                - content: Slide content dict with keys slide_1_cover through
                    slide_12_next_steps. Each slide contains placeholder field
                    values matching the expected layout.
                - raw_response: Original LLM response string.

        Raises:
            LLMError: If LLM call fails or response is not valid JSON.
        """
        # Convert deal analysis dict to JSON string for the prompt
        deal_analysis_text = json.dumps(deal_analysis, indent=2)

        messages = [
            {"role": "system", "content": PROPOSAL_DECK_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": format_proposal_deck_prompt(deal_analysis_text),
            },
        ]

        raw = self.generate(messages)
        parsed = self._extract_json(raw)

        # Validate expected slide keys are present
        expected_keys = [
            "slide_1_cover",
            "slide_2_executive_summary",
            "slide_3_client_context",
            "slide_4_challenges",
            "slide_5_proposed_solution",
            "slide_6_solution_scope",
            "slide_7_implementation",
            "slide_8_value_case",
            "slide_9_commercials",
            "slide_10_risk_mitigation",
            "slide_11_proof_of_success",
            "slide_12_next_steps",
        ]

        missing_slides = [key for key in expected_keys if key not in parsed]
        if missing_slides:
            logger.warning(
                "LLM response missing slide keys: %s",
                ", ".join(missing_slides),
            )

        # Validate each slide value is a dict
        for key in expected_keys:
            if key in parsed and not isinstance(parsed[key], dict):
                raise LLMError(
                    f"{key} field is not an object",
                    error_type="LLM_INVALID",
                )

        logger.info(
            "Proposal deck content generated (%d/%d slides)",
            len(expected_keys) - len(missing_slides),
            len(expected_keys),
        )

        return {
            "content": parsed,
            "raw_response": raw,
        }

    def summarize_chunk(
        self,
        chunk: str,
        use_cloud: bool = False,
    ) -> str:
        """Summarize a transcript chunk.

        Used for processing large transcripts that exceed the context window.
        Each chunk is summarized independently, then summaries are combined.

        Args:
            chunk: Text chunk to summarize.
            use_cloud: Ignored. Kept for handler compatibility.

        Returns:
            Summary of the chunk as a string.

        Raises:
            LLMError: If LLM call fails.
        """
        if not chunk or not chunk.strip():
            return ""

        messages = [
            {"role": "system", "content": SUMMARIZE_CHUNK_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": SUMMARIZE_CHUNK_USER_PROMPT.format(chunk=chunk),
            },
        ]

        summary = self.generate(messages, temperature=0.2)
        logger.debug(
            "Chunk summarized: %d tokens -> %d tokens",
            count_tokens(chunk),
            count_tokens(summary),
        )
        return summary

    def _prepare_transcript_for_analysis(
        self,
        transcript: str | list[str],
        use_cloud: bool = False,
    ) -> str:
        """Prepare transcript for analysis, chunking and summarizing if needed.

        If the transcript exceeds CHUNK_SUMMARIZE_THRESHOLD tokens, it is:
        1. Split into chunks of ~CHUNK_SIZE_TOKENS each
        2. Each chunk is summarized
        3. Summaries are combined into a single condensed transcript

        Args:
            transcript: Raw transcript text or list of transcript texts.
            use_cloud: Ignored. Kept for compatibility.

        Returns:
            Transcript text ready for analysis (original or summarized).
        """
        # Merge multiple transcripts if provided as list
        if isinstance(transcript, list):
            merged = "\n\n---\n\n".join(t.strip() for t in transcript if t.strip())
        else:
            merged = transcript.strip()

        if not merged:
            return ""

        total_tokens = count_tokens(merged)

        # If under threshold, return as-is
        if total_tokens <= self.CHUNK_SUMMARIZE_THRESHOLD:
            logger.debug(
                "Transcript under threshold (%d tokens), no chunking needed",
                total_tokens,
            )
            return merged

        # Chunk and summarize
        logger.info(
            "Transcript exceeds threshold (%d > %d tokens), chunking and summarizing",
            total_tokens,
            self.CHUNK_SUMMARIZE_THRESHOLD,
        )

        chunks = chunk_text(merged, self.CHUNK_SIZE_TOKENS)
        logger.info("Split transcript into %d chunks", len(chunks))

        summaries: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            logger.info(
                "Summarizing chunk %d/%d (%d tokens)",
                i,
                len(chunks),
                count_tokens(chunk),
            )
            summary = self.summarize_chunk(chunk)
            if summary:
                summaries.append(f"## Summary of Part {i}\n\n{summary}")

        combined = "\n\n---\n\n".join(summaries)
        combined_tokens = count_tokens(combined)

        logger.info(
            "Transcript condensed: %d tokens -> %d tokens (%d%% reduction)",
            total_tokens,
            combined_tokens,
            int((1 - combined_tokens / total_tokens) * 100),
        )

        return combined

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract and parse JSON from LLM response text.

        Handles responses wrapped in markdown code fences
        (```json ... ``` or ``` ... ```).

        Args:
            text: Raw LLM response text.

        Returns:
            Parsed JSON as a dict.

        Raises:
            LLMError: If no valid JSON can be extracted.
        """
        # Try stripping markdown code fences first
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        candidate = fenced.group(1) if fenced else text

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            # Fall back to raw text if fence extraction didn't work
            if fenced:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise LLMError(
                        f"LLM response is not valid JSON: {exc}",
                        error_type="LLM_INVALID",
                    ) from exc
            else:
                raise LLMError(
                    "LLM response is not valid JSON",
                    error_type="LLM_INVALID",
                )

        if not isinstance(data, dict):
            raise LLMError(
                "LLM response JSON is not an object",
                error_type="LLM_INVALID",
            )

        return data  # type: ignore[return-value]

    def _call_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> str:
        """Call Anthropic API with exponential backoff retry.

        Converts OpenAI-style messages to Anthropic format (extracting
        system prompt separately). Retries on transient errors.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If all retries fail or response is invalid.
        """
        # Convert OpenAI message format to Anthropic format
        system_content = ""
        anthropic_messages: list[dict[str, str]] = []

        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                anthropic_messages.append(
                    {
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                )

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=8192,
                    system=system_content,
                    messages=anthropic_messages,
                    temperature=temperature,
                )

                # Extract text from response content blocks
                content_parts = []
                for block in response.content:
                    if hasattr(block, "text"):
                        content_parts.append(block.text)

                content = "".join(content_parts)

                if not content or not content.strip():
                    raise LLMError(
                        "LLM returned empty response",
                        error_type="LLM_INVALID",
                    )

                self._log_usage(attempt + 1, response.usage)
                return content

            except LLMError:
                raise  # Don't retry invalid responses

            except anthropic.APIConnectionError as exc:
                last_error = exc
                logger.error(
                    "LLM connection failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    exc,
                )
                if attempt == self.MAX_RETRIES - 1:
                    raise LLMError(
                        f"Cannot connect to LLM service: {exc}",
                        error_type="LLM_OFFLINE",
                    ) from exc

            except (anthropic.APIStatusError, anthropic.APITimeoutError) as exc:
                last_error = exc
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    exc,
                )

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Unexpected LLM error (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    exc,
                )

            # Sleep before next attempt
            if attempt < self.MAX_RETRIES - 1:
                sleep_time = self.BACKOFF_SECONDS[attempt]
                logger.info("Retrying in %ds...", sleep_time)
                time.sleep(sleep_time)

        raise LLMError(
            f"LLM request failed after {self.MAX_RETRIES} attempts: {last_error}",
            error_type="LLM_ERROR",
        ) from last_error

    @staticmethod
    def _log_usage(attempt: int, usage: Any) -> None:
        """Log token usage from LLM response.

        Args:
            attempt: Which attempt number succeeded.
            usage: Usage object from the Anthropic response.
        """
        if usage:
            logger.info(
                "LLM response (attempt %d, prompt=%d, completion=%d tokens)",
                attempt,
                usage.input_tokens,
                usage.output_tokens,
            )
        else:
            logger.info("LLM response (attempt %d, usage not reported)", attempt)
