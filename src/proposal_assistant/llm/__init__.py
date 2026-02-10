"""LLM integration module for Proposal Assistant."""

from proposal_assistant.llm.agent import (
    LLMError,
    generate_deal_analysis,
    generate_proposal_content,
    get_agent_options,
    _extract_json,
    _prepare_transcript,
    _summarize_chunk,
)
from proposal_assistant.llm.context_builder import (
    ContextBuilder,
    ContextBuildResult,
    StatusCallbackFn,
    SummarizerFn,
    chunk_text,
    count_tokens,
)

__all__ = [
    "ContextBuilder",
    "ContextBuildResult",
    "LLMError",
    "StatusCallbackFn",
    "SummarizerFn",
    "_extract_json",
    "_prepare_transcript",
    "_summarize_chunk",
    "chunk_text",
    "count_tokens",
    "generate_deal_analysis",
    "generate_proposal_content",
    "get_agent_options",
]
