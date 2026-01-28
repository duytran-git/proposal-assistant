"""LLM client for Proposal Assistant using OpenAI-compatible API."""

import json
import logging
import re
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from proposal_assistant.config import Config
from proposal_assistant.llm.context_builder import ContextBuilder
from proposal_assistant.llm.prompts.deal_analysis import SYSTEM_PROMPT, format_user_prompt

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


class LLMClient:
    """LLM API client connecting to Ollama via OpenAI-compatible SDK.

    Uses the openai SDK pointed at Ollama's /v1 endpoint.
    Implements retry with exponential backoff for transient failures.

    Attributes:
        MAX_RETRIES: Maximum number of retry attempts.
        BACKOFF_SECONDS: Sleep durations between retries.
    """

    MAX_RETRIES: int = 3
    BACKOFF_SECONDS: list[int] = [1, 2, 4]

    def __init__(self, config: Config) -> None:
        """Initialize the LLM client.

        Args:
            config: Application configuration with Ollama connection details.
        """
        self._client = OpenAI(
            base_url=config.ollama_base_url,
            api_key="ollama",  # Ollama doesn't require a real key
        )
        self._model = config.ollama_model
        self._num_ctx = config.ollama_num_ctx

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> str:
        """Generate a completion from the LLM.

        Args:
            messages: Chat messages in OpenAI format
                (list of {"role": ..., "content": ...}).
            temperature: Sampling temperature (default: 0.3).

        Returns:
            The LLM response text.

        Raises:
            LLMError: If all retries are exhausted or response is invalid.
        """
        return self._call_with_retry(messages, temperature=temperature)

    def generate_deal_analysis(
        self,
        transcript: str,
        references: list[str] | None = None,
        web_content: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a Deal Analysis from transcript and supporting materials.

        Assembles context within token limits, sends to LLM with the
        deal analysis prompt, and parses the structured JSON response.

        Args:
            transcript: Meeting transcript text.
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
        builder = ContextBuilder()
        result = builder.build_context(
            transcript=transcript,
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
        """Call LLM with exponential backoff retry.

        Retries on transient errors (connection, timeout, server errors).
        Does not retry on invalid responses (empty content).

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If all retries fail or response is invalid.
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    extra_body={"options": {"num_ctx": self._num_ctx}},
                )

                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise LLMError(
                        "LLM returned empty response",
                        error_type="LLM_INVALID",
                    )

                self._log_usage(attempt + 1, response.usage)
                return content

            except LLMError:
                raise  # Don't retry invalid responses

            except APIConnectionError as exc:
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

            except (APIStatusError, APITimeoutError) as exc:
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
            usage: Usage object from the OpenAI response.
        """
        if usage:
            logger.info(
                "LLM response (attempt %d, prompt=%d, completion=%d tokens)",
                attempt,
                usage.prompt_tokens,
                usage.completion_tokens,
            )
        else:
            logger.info("LLM response (attempt %d, usage not reported)", attempt)
