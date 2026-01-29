"""Document parsing utilities for extracting content from various file formats."""

from io import BytesIO


def parse_docx(content: bytes) -> str:
    """Parse .docx file content and extract text.

    Args:
        content: Raw bytes of the .docx file.

    Returns:
        Extracted text content from the document.

    Raises:
        ValueError: If the document cannot be parsed.
    """
    from docx import Document

    try:
        doc = Document(BytesIO(content))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"Failed to parse .docx file: {e}") from e


def parse_markdown(content: str) -> str:
    """Parse .md file content.

    Args:
        content: String content of the .md file.

    Returns:
        The markdown content (passed through as-is).
    """
    return content
