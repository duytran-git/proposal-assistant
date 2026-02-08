"""Parser for Deal Analysis documents uploaded by users.

Handles both .docx (via python-docx) and .md formats, attempting to
extract structured content matching the DealAnalysisContent schema.
"""

import json
import logging
import re
from typing import Any

from proposal_assistant.utils.document_parser import parse_docx, parse_markdown

logger = logging.getLogger(__name__)

# Expected sections in Deal Analysis structure
DEAL_ANALYSIS_SECTIONS = [
    "opportunity_snapshot",
    "problem_impact",
    "current_desired_state",
    "buying_dynamics",
    "renessai_fit",
    "proof_next_actions",
]

# Section header patterns for markdown extraction
SECTION_PATTERNS = {
    "opportunity_snapshot": r"(?i)opportunity\s*snapshot|company\s*overview",
    "problem_impact": r"(?i)problem\s*(?:&|and)?\s*impact|business\s*impact",
    "current_desired_state": r"(?i)current\s*(?:&|and)?\s*desired\s*state|current\s*state",
    "buying_dynamics": r"(?i)buying\s*dynamics|stakeholders|decision\s*process",
    "renessai_fit": r"(?i)renessai\s*fit|solution\s*fit|how\s*renessai",
    "proof_next_actions": r"(?i)proof\s*(?:&|and)?\s*next\s*(?:actions|steps)|next\s*steps",
}


def parse_deal_analysis(content: bytes | str, filename: str = "") -> dict[str, Any]:
    """Parse uploaded document into DealAnalysisContent structure.

    Supports three formats:
    1. JSON: If content is valid JSON matching expected schema
    2. Markdown (.md): Extracts sections by headers
    3. Word (.docx): Extracts text then parses as markdown

    Args:
        content: Raw file bytes (.docx) or string content (.md).
        filename: Original filename to determine format. If empty,
            attempts auto-detection.

    Returns:
        Dict matching DealAnalysisContent structure:
        {
            "opportunity_snapshot": {...},
            "problem_impact": {...},
            "current_desired_state": {...},
            "buying_dynamics": {...},
            "renessai_fit": {...},
            "proof_next_actions": {...},
        }
        Any section not found will have value "Unknown / Not provided".

    Raises:
        ValueError: If content cannot be parsed.
    """
    # 1. Extract text based on file type
    if isinstance(content, bytes):
        if filename.lower().endswith(".md"):
            text = content.decode("utf-8")
        else:
            # Assume .docx for bytes without .md extension
            text = parse_docx(content)
    else:
        text = parse_markdown(content)

    # 2. Try parsing as JSON first (user might provide structured output)
    json_result = _try_parse_json(text)
    if json_result:
        logger.info("Parsed deal analysis from JSON format")
        return json_result

    # 3. Parse as markdown with section headers
    result = _parse_markdown_sections(text)
    logger.info(
        "Parsed deal analysis from markdown (%d sections found)",
        sum(1 for v in result.values() if v != "Unknown / Not provided"),
    )
    return result


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Attempt to parse text as JSON deal analysis.

    Handles JSON wrapped in markdown code fences.

    Args:
        text: Text that might contain JSON.

    Returns:
        Parsed deal analysis dict if valid JSON, None otherwise.
    """
    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text.strip()

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Handle nested {"deal_analysis": {...}} structure
    if "deal_analysis" in data and isinstance(data["deal_analysis"], dict):
        data = data["deal_analysis"]

    # Validate it has at least some expected sections
    has_sections = any(section in data for section in DEAL_ANALYSIS_SECTIONS)
    if not has_sections:
        return None

    # Fill missing sections with default value
    result = {}
    for section in DEAL_ANALYSIS_SECTIONS:
        result[section] = data.get(section, "Unknown / Not provided")

    return result


def _parse_markdown_sections(text: str) -> dict[str, Any]:
    """Parse markdown text by extracting content under section headers.

    Looks for headers matching known section patterns and extracts
    all content until the next header.

    Args:
        text: Markdown-formatted text.

    Returns:
        Dict with section content. Missing sections have default value.
    """
    result: dict[str, Any] = {}

    # Split text into lines for processing
    lines = text.split("\n")

    # Find all header positions with their matched section
    header_positions: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        # Match markdown headers (# Header, ## Header, ### Header)
        header_match = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if not header_match:
            continue

        header_text = header_match.group(1)

        # Check if this header matches any known section
        for section, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, header_text):
                header_positions.append((i, section))
                break

    # Extract content between headers
    for idx, (line_num, section) in enumerate(header_positions):
        # Find the end of this section (start of next header or end of file)
        if idx + 1 < len(header_positions):
            end_line = header_positions[idx + 1][0]
        else:
            end_line = len(lines)

        # Extract content (skip the header line itself)
        section_lines = lines[line_num + 1 : end_line]
        content = "\n".join(section_lines).strip()

        if content:
            result[section] = content

    # Fill missing sections with default value
    for section in DEAL_ANALYSIS_SECTIONS:
        if section not in result:
            result[section] = "Unknown / Not provided"

    return result
