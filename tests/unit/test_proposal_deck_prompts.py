"""Unit tests for proposal deck prompts module."""

from proposal_assistant.llm.prompts.proposal_deck import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    format_user_prompt,
)


class TestFormatUserPrompt:
    """Tests for format_user_prompt function."""

    def test_substitutes_deal_analysis(self):
        """format_user_prompt substitutes deal_analysis into template."""
        deal_analysis = '{"company": "Acme Corp", "opportunity": "AI Platform"}'

        result = format_user_prompt(deal_analysis)

        assert deal_analysis in result
        assert "{deal_analysis}" not in result

    def test_preserves_template_structure(self):
        """Formatted prompt includes expected template sections."""
        result = format_user_prompt("test content")

        assert "## Required output (JSON)" in result
        assert "slide_1_cover" in result
        assert "## Deal Analysis" in result

    def test_handles_multiline_deal_analysis(self):
        """Works with multiline deal analysis content."""
        multiline = """Line 1
        Line 2
        Line 3"""

        result = format_user_prompt(multiline)

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result


class TestPromptConstants:
    """Tests for prompt template constants."""

    def test_system_prompt_exists_and_not_empty(self):
        """SYSTEM_PROMPT is defined and non-empty."""
        assert SYSTEM_PROMPT
        assert len(SYSTEM_PROMPT) > 100

    def test_user_template_has_placeholder(self):
        """USER_TEMPLATE contains the deal_analysis placeholder."""
        assert "{deal_analysis}" in USER_TEMPLATE
