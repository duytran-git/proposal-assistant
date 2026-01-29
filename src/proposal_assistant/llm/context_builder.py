"""Context builder for assembling LLM input within token budget."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextBuildResult:
    """Result of context assembly.

    Attributes:
        context: The assembled context string ready for LLM input.
        transcript_included: Whether transcript content was included.
        transcript_truncated: Whether the transcript was truncated.
        transcript_original_tokens: Estimated token count of original transcript.
        references_included_count: Number of reference items included.
        references_total_count: Total number of reference items provided.
        web_included_count: Number of web content items included.
        web_total_count: Total number of web content items provided.
        estimated_tokens: Estimated total token count of the assembled context.
    """

    context: str
    transcript_included: bool
    transcript_truncated: bool
    transcript_original_tokens: int
    references_included_count: int
    references_total_count: int
    web_included_count: int
    web_total_count: int
    estimated_tokens: int


class ContextBuilder:
    """Assembles transcript, references, and web content within token limits.

    Uses character-based token estimation (~4 chars per token) appropriate
    for the qwen2.5:14b model on Ollama. Token limits are guidelines from
    the technical design with generous output reserve.

    Attributes:
        MAX_TRANSCRIPT_TOKENS: Maximum token budget for transcript content.
        MAX_REFERENCES_TOKENS: Maximum token budget for reference materials.
        MAX_WEB_TOKENS: Maximum token budget for web research content.
        RESERVED_OUTPUT_TOKENS: Tokens reserved for LLM output generation.
        CHARS_PER_TOKEN: Character-to-token ratio for estimation.
    """

    MAX_TRANSCRIPT_TOKENS: int = 24_000
    MAX_REFERENCES_TOKENS: int = 10_000
    MAX_WEB_TOKENS: int = 6_000
    RESERVED_OUTPUT_TOKENS: int = 8_000
    CHARS_PER_TOKEN: int = 4

    def build_context(
        self,
        transcript: str | list[str],
        references: list[str] | None = None,
        web_content: list[str] | None = None,
    ) -> ContextBuildResult:
        """Assemble context from transcript(s), references, and web content.

        Each input type has an independent token budget. Content exceeding
        the budget is truncated at line boundaries. Multiple references
        and web content items share their budget using equal-share
        splitting with greedy carry-forward.

        Args:
            transcript: Meeting transcript text, or list of transcripts to merge.
                Multiple transcripts are merged with "--- Transcript N ---" markers.
            references: List of reference document texts.
            web_content: List of web page content texts.

        Returns:
            ContextBuildResult with assembled context and metadata.
        """
        refs = references or []
        web = web_content or []

        max_transcript_chars = self.MAX_TRANSCRIPT_TOKENS * self.CHARS_PER_TOKEN
        max_refs_chars = self.MAX_REFERENCES_TOKENS * self.CHARS_PER_TOKEN
        max_web_chars = self.MAX_WEB_TOKENS * self.CHARS_PER_TOKEN

        # Merge multiple transcripts with markers
        merged_transcript = self._merge_transcripts(transcript)

        # Transcript
        transcript_stripped = merged_transcript.strip()
        transcript_original_tokens = self._estimate_tokens(transcript_stripped)
        transcript_included = bool(transcript_stripped)

        if not transcript_included:
            logger.warning("Empty transcript provided to context builder")
            transcript_text = ""
            transcript_truncated = False
        else:
            truncated, transcript_truncated = self._truncate_to_budget(
                transcript_stripped, max_transcript_chars
            )
            if transcript_truncated:
                logger.warning(
                    "Transcript truncated from ~%d to ~%d tokens",
                    transcript_original_tokens,
                    self._estimate_tokens(truncated),
                )
            transcript_text = f"## TRANSCRIPT\n\n{truncated}"

        # References
        refs_text, refs_included = self._build_section(
            refs, max_refs_chars, "## REFERENCE MATERIALS", "### Reference"
        )

        # Web content
        web_text, web_included = self._build_section(
            web, max_web_chars, "## WEB RESEARCH", "### Source"
        )

        # Assemble sections
        sections = [s for s in [transcript_text, refs_text, web_text] if s]
        context = "\n\n---\n\n".join(sections)

        estimated_tokens = self._estimate_tokens(context)
        logger.info(
            "Context built: ~%d tokens "
            "(transcript=%s, refs=%d/%d, web=%d/%d)",
            estimated_tokens,
            "truncated" if transcript_truncated else "full",
            refs_included,
            len(refs),
            web_included,
            len(web),
        )

        return ContextBuildResult(
            context=context,
            transcript_included=transcript_included,
            transcript_truncated=transcript_truncated,
            transcript_original_tokens=transcript_original_tokens,
            references_included_count=refs_included,
            references_total_count=len(refs),
            web_included_count=web_included,
            web_total_count=len(web),
            estimated_tokens=estimated_tokens,
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using character-based approximation.

        Args:
            text: Input text to estimate.

        Returns:
            Estimated number of tokens (~4 chars per token).
        """
        return len(text) // self.CHARS_PER_TOKEN

    @staticmethod
    def _merge_transcripts(transcript: str | list[str]) -> str:
        """Merge multiple transcripts with numbered separators.

        Args:
            transcript: Single transcript string or list of transcript strings.

        Returns:
            Merged transcript with "--- Transcript N ---" markers between files.
        """
        if isinstance(transcript, str):
            return transcript

        # Filter out empty transcripts
        non_empty = [t.strip() for t in transcript if t.strip()]
        if not non_empty:
            return ""

        if len(non_empty) == 1:
            return non_empty[0]

        # Merge with numbered markers
        parts = []
        for i, content in enumerate(non_empty, start=1):
            parts.append(f"--- Transcript {i} ---\n\n{content}")

        return "\n\n".join(parts)

    def _truncate_to_budget(
        self, text: str, max_chars: int
    ) -> tuple[str, bool]:
        """Truncate text to fit within character budget at line boundary.

        Finds the last newline within the budget and truncates there.
        Falls back to word boundary, then hard truncation.

        Args:
            text: Text to potentially truncate.
            max_chars: Maximum allowed characters.

        Returns:
            Tuple of (truncated_text, was_truncated).
        """
        if len(text) <= max_chars:
            return text, False

        slice_ = text[:max_chars]

        # Prefer line boundary
        pos = slice_.rfind("\n")
        if pos > 0:
            return slice_[:pos], True

        # Fall back to word boundary
        pos = slice_.rfind(" ")
        if pos > 0:
            return slice_[:pos], True

        # Hard truncate
        return slice_, True

    def _build_section(
        self,
        items: list[str],
        max_chars: int,
        section_header: str,
        item_prefix: str,
    ) -> tuple[str, int]:
        """Build a context section from multiple items within budget.

        Distributes budget equally across items with greedy carry-forward:
        if an item uses less than its share, the remainder is available
        for subsequent items.

        Args:
            items: List of text items to include.
            max_chars: Total character budget for this section.
            section_header: Markdown header (e.g., "## REFERENCE MATERIALS").
            item_prefix: Prefix for each item (e.g., "### Reference").

        Returns:
            Tuple of (section_text, items_included_count).
        """
        # Filter empty items
        non_empty = [(i, item.strip()) for i, item in enumerate(items) if item.strip()]
        if not non_empty:
            return "", 0

        header_overhead = len(section_header) + 2  # header + "\n\n"
        available = max_chars - header_overhead
        if available <= 0:
            return "", 0

        per_item = available // len(non_empty)
        parts: list[str] = []
        remaining = available

        for idx, (original_idx, content) in enumerate(non_empty):
            item_header = f"{item_prefix} {idx + 1}\n"
            item_header_len = len(item_header)

            content_budget = min(remaining - item_header_len, per_item)
            if content_budget <= 0:
                break

            truncated, _ = self._truncate_to_budget(content, content_budget)
            part = item_header + truncated
            parts.append(part)

            used = len(part)
            remaining -= used

            # Recalculate per-item for remaining items (greedy carry-forward)
            items_left = len(non_empty) - (idx + 1)
            if items_left > 0:
                per_item = remaining // items_left

        if not parts:
            return "", 0

        section = section_header + "\n\n" + "\n\n".join(parts)
        return section, len(parts)
