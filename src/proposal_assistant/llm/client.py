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
from proposal_assistant.llm.prompts.proposal_deck import (
    SYSTEM_PROMPT as PROPOSAL_DECK_SYSTEM_PROMPT,
    format_user_prompt as format_proposal_deck_prompt,
)

# Optional imports for cloud providers
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

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
    Supports fallback to cloud providers (OpenAI or Anthropic) when local
    Ollama is unavailable and user has given consent.
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
            config: Application configuration with Ollama and cloud provider details.
        """
        # Local Ollama client
        self._client = OpenAI(
            base_url=config.ollama_base_url,
            api_key="ollama",  # Ollama doesn't require a real key
        )
        self._model = config.ollama_model
        self._num_ctx = config.ollama_num_ctx

        # Cloud provider configuration
        self._cloud_provider = config.cloud_provider
        self._cloud_client: OpenAI | Any | None = None
        self._cloud_model: str | None = None

        # Initialize cloud client if configured
        if config.cloud_provider == "openai" and config.openai_api_key:
            self._cloud_client = OpenAI(api_key=config.openai_api_key)
            self._cloud_model = config.openai_model
            logger.info("Cloud fallback configured: OpenAI (%s)", config.openai_model)
        elif config.cloud_provider == "anthropic" and config.anthropic_api_key:
            if not ANTHROPIC_AVAILABLE:
                logger.warning("Anthropic configured but SDK not installed")
            else:
                self._cloud_client = anthropic.Anthropic(api_key=config.anthropic_api_key)
                self._cloud_model = config.anthropic_model
                logger.info("Cloud fallback configured: Anthropic (%s)", config.anthropic_model)

    @property
    def cloud_available(self) -> bool:
        """Check if cloud provider is configured and available."""
        return self._cloud_client is not None

    def check_ollama_health(self) -> bool:
        """Check if Ollama service is healthy by pinging /v1/models endpoint.

        Returns:
            True if Ollama responds successfully, False otherwise.
        """
        try:
            self._client.models.list()
            logger.debug("Ollama health check passed")
            return True
        except Exception as e:
            logger.warning("Ollama health check failed: %s", e)
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
            use_cloud: If True, use cloud provider instead of local Ollama.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If all retries are exhausted or response is invalid.
        """
        if use_cloud:
            return self._call_cloud(messages, temperature=temperature)
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

        Args:
            transcript: Meeting transcript text, or list of transcript texts.
            references: Optional reference document texts.
            web_content: Optional web research content texts.
            use_cloud: If True, use cloud provider instead of local Ollama.

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

        raw = self.generate(messages, use_cloud=use_cloud)
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
            use_cloud: If True, use cloud provider instead of local Ollama.

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
            {"role": "user", "content": format_proposal_deck_prompt(deal_analysis_text)},
        ]

        raw = self.generate(messages, use_cloud=use_cloud)
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

    def _call_cloud(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> str:
        """Call cloud LLM provider with retry logic.

        Supports OpenAI and Anthropic APIs.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.

        Returns:
            The LLM response text.

        Raises:
            LLMError: If cloud provider is not configured or call fails.
        """
        if not self._cloud_client or not self._cloud_model:
            raise LLMError(
                "Cloud provider not configured",
                error_type="LLM_ERROR",
            )

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                if self._cloud_provider == "anthropic":
                    content = self._call_anthropic(messages, temperature)
                else:
                    # OpenAI or OpenAI-compatible
                    content = self._call_openai_cloud(messages, temperature)

                if not content or not content.strip():
                    raise LLMError(
                        "Cloud LLM returned empty response",
                        error_type="LLM_INVALID",
                    )

                logger.info(
                    "Cloud LLM response (attempt %d, provider=%s)",
                    attempt + 1,
                    self._cloud_provider,
                )
                return content

            except LLMError:
                raise  # Don't retry invalid responses

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Cloud LLM request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    exc,
                )

            # Sleep before next attempt
            if attempt < self.MAX_RETRIES - 1:
                sleep_time = self.BACKOFF_SECONDS[attempt]
                logger.info("Retrying cloud LLM in %ds...", sleep_time)
                time.sleep(sleep_time)

        raise LLMError(
            f"Cloud LLM request failed after {self.MAX_RETRIES} attempts: {last_error}",
            error_type="LLM_ERROR",
        ) from last_error

    def _call_openai_cloud(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str:
        """Call OpenAI cloud API.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.

        Returns:
            The response content text.
        """
        response = self._cloud_client.chat.completions.create(
            model=self._cloud_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> str:
        """Call Anthropic Claude API.

        Converts OpenAI message format to Anthropic format.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.

        Returns:
            The response content text.
        """
        # Extract system message and convert remaining to Anthropic format
        system_content = ""
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        response = self._cloud_client.messages.create(
            model=self._cloud_model,
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

        return "".join(content_parts)
