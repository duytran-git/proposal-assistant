"""Anthropic API client wrapper for Proposal Assistant.

Provides async functions for generating Deal Analysis and Proposal Deck
content using the Anthropic Python SDK (direct HTTP API calls).
Matches the return shapes of the old LLMClient so downstream code
(docs/deal_analysis.py, slides/proposal_deck.py) does not break.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import anthropic

from proposal_assistant.llm.context_builder import (
    ContextBuilder,
    chunk_text,
    count_tokens,
)
from proposal_assistant.llm.prompts.deal_analysis import (
    SYSTEM_PROMPT as DEAL_ANALYSIS_SYSTEM_PROMPT,
    format_user_prompt as format_deal_analysis_prompt,
)
from proposal_assistant.llm.prompts.proposal_deck import (
    SYSTEM_PROMPT as PROPOSAL_DECK_SYSTEM_PROMPT,
    format_user_prompt as format_proposal_deck_prompt,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-5-20250929"
MAX_RETRIES: int = 3
BACKOFF_SECONDS: list[int] = [1, 2, 4]
CHUNK_SUMMARIZE_THRESHOLD: int = 32_000
CHUNK_SIZE_TOKENS: int = 8_000

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Chunk summarization prompts (same as the old client)
_SUMMARIZE_CHUNK_SYSTEM = (
    "You are a meeting transcript summarizer. Create a concise but "
    "comprehensive summary. Focus on key discussion topics, decisions, "
    "action items, business details, problems, and proposed solutions. "
    "Preserve specific names, numbers, dates, and technical terms exactly."
)

_SUMMARIZE_CHUNK_USER = (
    "Summarize the following transcript chunk:\n\n{chunk}\n\n"
    "Provide a comprehensive summary that captures all important information."
)


# ---------------------------------------------------------------------------
# LLMError
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when an LLM operation fails.

    Attributes:
        error_type: Error code matching the error handling matrix
            (LLM_ERROR, LLM_INVALID, LLM_OFFLINE).
    """

    def __init__(self, message: str, error_type: str = "LLM_ERROR") -> None:
        self.error_type = error_type
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_system_prompt() -> str:
    """Read the general system prompt from prompts/system_sales_advisor.txt."""
    prompt_path = _PROMPTS_DIR / "system_sales_advisor.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _extract_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM response text.

    Handles responses wrapped in markdown code fences
    (``\\`json ... \\`` or ``\\` ... \\``).

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed JSON as a dict.

    Raises:
        LLMError: If no valid JSON can be extracted.
    """
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
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


# ---------------------------------------------------------------------------
# Anthropic client helper
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Return a cached Anthropic client (uses ANTHROPIC_API_KEY env var)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ---------------------------------------------------------------------------
# Async query helper with retry + exponential backoff
# ---------------------------------------------------------------------------


async def _query_with_retry(
    prompt: str,
    system_prompt: str,
    temperature: float = 0.3,
) -> str:
    """Execute an Anthropic messages.create call with retry.

    Retries on transient errors with exponential backoff (1s, 2s, 4s).
    Does NOT retry on ``LLMError`` (invalid/empty responses).

    Args:
        prompt: The user prompt to send.
        system_prompt: System prompt for the query.
        temperature: Sampling temperature.

    Returns:
        The LLM response text.

    Raises:
        LLMError: If all retries fail or response is invalid/empty.
    """
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            client = _get_client()
            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text if response.content else ""

            if not result_text or not result_text.strip():
                raise LLMError(
                    "LLM returned empty response",
                    error_type="LLM_INVALID",
                )

            logger.info("LLM response received (attempt %d)", attempt + 1)
            return result_text

        except LLMError:
            raise  # Don't retry invalid responses

        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM request failed (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES,
                exc,
            )

            if attempt < MAX_RETRIES - 1:
                sleep_time = BACKOFF_SECONDS[attempt]
                logger.info("Retrying in %ds...", sleep_time)
                await asyncio.sleep(sleep_time)

    raise LLMError(
        f"LLM request failed after {MAX_RETRIES} attempts: {last_error}",
        error_type="LLM_ERROR",
    ) from last_error


# ---------------------------------------------------------------------------
# Transcript preparation (async — chunk summarization calls the LLM)
# ---------------------------------------------------------------------------


async def _summarize_chunk(chunk: str) -> str:
    """Summarize a single transcript chunk via the LLM.

    Args:
        chunk: Text chunk to summarize.

    Returns:
        Summary string, or empty string if the chunk was empty.
    """
    if not chunk or not chunk.strip():
        return ""

    prompt = _SUMMARIZE_CHUNK_USER.format(chunk=chunk)
    return await _query_with_retry(prompt, system_prompt=_SUMMARIZE_CHUNK_SYSTEM, temperature=0.2)


async def _prepare_transcript(transcript: str | list[str]) -> str:
    """Merge multiple transcripts and chunk-summarize if over threshold.

    Args:
        transcript: Raw transcript text, or list of transcript texts.

    Returns:
        Transcript text ready for analysis (original or summarized).
    """
    if isinstance(transcript, list):
        merged = "\n\n---\n\n".join(t.strip() for t in transcript if t.strip())
    else:
        merged = transcript.strip()

    if not merged:
        return ""

    total_tokens = count_tokens(merged)
    if total_tokens <= CHUNK_SUMMARIZE_THRESHOLD:
        logger.debug(
            "Transcript under threshold (%d tokens), no chunking needed",
            total_tokens,
        )
        return merged

    logger.info(
        "Transcript exceeds threshold (%d > %d tokens), chunking and summarizing",
        total_tokens,
        CHUNK_SUMMARIZE_THRESHOLD,
    )

    chunks = chunk_text(merged, CHUNK_SIZE_TOKENS)
    logger.info("Split transcript into %d chunks", len(chunks))

    summaries: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info(
            "Summarizing chunk %d/%d (%d tokens)",
            i,
            len(chunks),
            count_tokens(chunk),
        )
        summary = await _summarize_chunk(chunk)
        if summary:
            summaries.append(f"## Summary of Part {i}\n\n{summary}")

    combined = "\n\n---\n\n".join(summaries)
    combined_tokens = count_tokens(combined)

    logger.info(
        "Transcript condensed: %d tokens -> %d tokens (%d%% reduction)",
        total_tokens,
        combined_tokens,
        int((1 - combined_tokens / total_tokens) * 100) if total_tokens else 0,
    )

    return combined


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def generate_deal_analysis(
    transcript: str | list[str],
    references: list[str] | None = None,
    web_content: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a Deal Analysis from transcript and supporting materials.

    Assembles context within token limits, sends to LLM with the
    deal-analysis prompt, and parses the structured JSON response.

    Args:
        transcript: Meeting transcript text, or list of transcript texts.
        references: Optional reference document texts.
        web_content: Optional web research content texts.

    Returns:
        Dict with keys:
            - content: Parsed deal_analysis object (dict).
            - missing_info: List of missing information labels.
            - raw_response: Original LLM response string.

    Raises:
        LLMError: If LLM call fails or response is not valid JSON.
    """
    prepared = await _prepare_transcript(transcript)

    builder = ContextBuilder()
    result = builder.build_context(
        transcript=prepared,
        references=references,
        web_content=web_content,
    )

    prompt = format_deal_analysis_prompt(result.context)
    raw = await _query_with_retry(prompt, system_prompt=DEAL_ANALYSIS_SYSTEM_PROMPT)
    parsed = _extract_json(raw)

    content = parsed.get("deal_analysis", {})
    missing_info = parsed.get("missing_info", [])

    if not isinstance(content, dict):
        raise LLMError(
            "deal_analysis field is not an object",
            error_type="LLM_INVALID",
        )
    if not isinstance(missing_info, list):
        missing_info = []

    logger.info("Deal analysis generated (%d missing items)", len(missing_info))

    return {
        "content": content,
        "missing_info": missing_info,
        "raw_response": raw,
    }


async def generate_proposal_content(
    deal_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Generate Proposal Deck slide content from a Deal Analysis.

    Transforms a Deal Analysis document into structured content
    for a 12-slide Proposal Deck.

    Args:
        deal_analysis: Parsed deal_analysis dict from generate_deal_analysis().

    Returns:
        Dict with keys:
            - content: Slide content dict with keys slide_1_cover through
                slide_12_next_steps.
            - raw_response: Original LLM response string.

    Raises:
        LLMError: If LLM call fails or response is not valid JSON.
    """
    deal_analysis_text = json.dumps(deal_analysis, indent=2)
    prompt = format_proposal_deck_prompt(deal_analysis_text)
    raw = await _query_with_retry(prompt, system_prompt=PROPOSAL_DECK_SYSTEM_PROMPT)
    parsed = _extract_json(raw)

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

    missing_slides = [k for k in expected_keys if k not in parsed]
    if missing_slides:
        logger.warning(
            "LLM response missing slide keys: %s",
            ", ".join(missing_slides),
        )

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
