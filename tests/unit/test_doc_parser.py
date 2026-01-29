"""Unit tests for doc_parser utility."""

import json

import pytest

from proposal_assistant.utils.doc_parser import (
    DEAL_ANALYSIS_SECTIONS,
    parse_deal_analysis,
    _parse_markdown_sections,
    _try_parse_json,
)


class TestParseJsonFormat:
    """Tests for JSON parsing in parse_deal_analysis."""

    def test_parses_valid_json_structure(self):
        """Parses valid JSON with all sections."""
        data = {
            "opportunity_snapshot": {"company": "Acme Corp"},
            "problem_impact": {"core_problem_statement": "Legacy systems"},
            "current_desired_state": {"current_state": "Manual processes"},
            "buying_dynamics": {"stakeholders_power_map": "CEO leads"},
            "renessai_fit": {"how_renessai_solves_top_pains": "Automation"},
            "proof_next_actions": {"next_steps": "Demo scheduled"},
        }
        content = json.dumps(data)

        result = parse_deal_analysis(content)

        assert result["opportunity_snapshot"] == {"company": "Acme Corp"}
        assert result["renessai_fit"] == {"how_renessai_solves_top_pains": "Automation"}

    def test_parses_nested_deal_analysis_key(self):
        """Parses JSON with nested deal_analysis key."""
        data = {
            "deal_analysis": {
                "opportunity_snapshot": {"company": "Test Inc"},
                "problem_impact": "Some impact",
            },
            "missing_info": ["Budget"],
        }
        content = json.dumps(data)

        result = parse_deal_analysis(content)

        assert result["opportunity_snapshot"] == {"company": "Test Inc"}
        assert result["problem_impact"] == "Some impact"

    def test_parses_json_in_code_fence(self):
        """Parses JSON wrapped in markdown code fence."""
        data = {"opportunity_snapshot": {"company": "Fenced Corp"}}
        content = f"```json\n{json.dumps(data)}\n```"

        result = parse_deal_analysis(content)

        assert result["opportunity_snapshot"] == {"company": "Fenced Corp"}

    def test_fills_missing_sections_with_default(self):
        """Missing sections get default value."""
        data = {"opportunity_snapshot": "Partial data"}
        content = json.dumps(data)

        result = parse_deal_analysis(content)

        assert result["opportunity_snapshot"] == "Partial data"
        assert result["problem_impact"] == "Unknown / Not provided"
        assert result["buying_dynamics"] == "Unknown / Not provided"


class TestTryParseJson:
    """Tests for _try_parse_json helper."""

    def test_returns_none_for_invalid_json(self):
        """Returns None when text is not valid JSON."""
        result = _try_parse_json("This is not JSON")
        assert result is None

    def test_returns_none_for_unrelated_json(self):
        """Returns None when JSON doesn't have expected sections."""
        result = _try_parse_json('{"unrelated": "data", "foo": "bar"}')
        assert result is None

    def test_returns_none_for_json_array(self):
        """Returns None when JSON is an array, not object."""
        result = _try_parse_json('[1, 2, 3]')
        assert result is None


class TestParseMarkdownSections:
    """Tests for markdown section parsing."""

    def test_extracts_sections_by_h2_headers(self):
        """Extracts content under ## headers."""
        text = """# Deal Analysis

## Opportunity Snapshot
Company: Acme Corp
Industry: Technology

## Problem & Impact
Core problem: Legacy systems
Business impact: $1M annually

## Current & Desired State
Current state: Manual processes
"""

        result = _parse_markdown_sections(text)

        assert "Company: Acme Corp" in result["opportunity_snapshot"]
        assert "Legacy systems" in result["problem_impact"]
        assert "Manual processes" in result["current_desired_state"]

    def test_extracts_sections_by_h3_headers(self):
        """Extracts content under ### headers."""
        text = """### Opportunity Snapshot
Test company data

### Buying Dynamics
Decision makers listed
"""

        result = _parse_markdown_sections(text)

        assert "Test company data" in result["opportunity_snapshot"]
        assert "Decision makers" in result["buying_dynamics"]

    def test_handles_alternative_header_names(self):
        """Recognizes alternative section header patterns."""
        text = """## Company Overview
Alternative name for opportunity snapshot

## Business Impact
Alternative name for problem impact

## Stakeholders
Alternative name for buying dynamics

## Solution Fit
Alternative name for renessai fit

## Next Steps
Final actions
"""

        result = _parse_markdown_sections(text)

        assert "Alternative name" in result["opportunity_snapshot"]
        assert "Alternative name" in result["problem_impact"]
        assert "Alternative name" in result["buying_dynamics"]
        assert "Alternative name" in result["renessai_fit"]
        assert "Final actions" in result["proof_next_actions"]

    def test_fills_missing_sections_with_default(self):
        """Sections not found get default value."""
        text = """## Opportunity Snapshot
Only this section exists
"""

        result = _parse_markdown_sections(text)

        assert "Only this section" in result["opportunity_snapshot"]
        assert result["problem_impact"] == "Unknown / Not provided"
        assert result["buying_dynamics"] == "Unknown / Not provided"

    def test_handles_empty_text(self):
        """Returns all defaults for empty text."""
        result = _parse_markdown_sections("")

        for section in DEAL_ANALYSIS_SECTIONS:
            assert result[section] == "Unknown / Not provided"


class TestParseDocx:
    """Tests for .docx parsing integration."""

    def test_invalid_docx_raises_error(self):
        """Raises ValueError for invalid .docx bytes."""
        with pytest.raises(ValueError, match="Failed to parse .docx file"):
            parse_deal_analysis(b"not a valid docx", filename="test.docx")

    def test_md_bytes_decoded_as_utf8(self):
        """Bytes with .md filename decoded as UTF-8."""
        md_content = "## Opportunity Snapshot\nTest content"
        result = parse_deal_analysis(md_content.encode("utf-8"), filename="test.md")

        assert "Test content" in result["opportunity_snapshot"]


class TestParseDealAnalysisIntegration:
    """Integration tests for parse_deal_analysis."""

    def test_complete_markdown_document(self):
        """Parses a complete markdown deal analysis document."""
        content = """# Deal Analysis: Acme Corp

## Opportunity Snapshot
- Company: Acme Corporation
- Industry: Manufacturing
- Size: 500 employees
- Contact: John Smith, CTO

## Problem & Impact
**Core Problem**: Outdated inventory management system
**Business Impact**: $2M in annual losses due to stockouts

## Current & Desired State
Current: Legacy ERP from 2005
Desired: Cloud-based real-time inventory

## Buying Dynamics
- Decision Maker: CFO (Sarah Johnson)
- Timeline: Q2 decision
- Budget: $500K allocated

## Renessai Fit
Our solution addresses:
- Real-time inventory tracking
- Integration with existing ERP

## Proof & Next Actions
- Schedule technical demo
- Provide ROI case study
"""

        result = parse_deal_analysis(content)

        assert "Acme Corporation" in result["opportunity_snapshot"]
        assert "$2M" in result["problem_impact"]
        assert "Legacy ERP" in result["current_desired_state"]
        assert "CFO" in result["buying_dynamics"]
        assert "Real-time inventory" in result["renessai_fit"]
        assert "technical demo" in result["proof_next_actions"]

    def test_prefers_json_over_markdown(self):
        """JSON format takes precedence over markdown parsing."""
        # Content that could be parsed as both JSON and markdown
        json_data = {"opportunity_snapshot": "JSON data"}
        content = f"""```json
{json.dumps(json_data)}
```

## Opportunity Snapshot
Markdown data
"""

        result = parse_deal_analysis(content)

        # Should use JSON data, not markdown
        assert result["opportunity_snapshot"] == "JSON data"

    def test_string_content_treated_as_markdown(self):
        """String content without filename treated as markdown."""
        content = "## Opportunity Snapshot\nPlain text content"

        result = parse_deal_analysis(content)

        assert "Plain text content" in result["opportunity_snapshot"]
