"""Validation utilities for transcript files."""

from dataclasses import dataclass
from typing import Optional

from proposal_assistant.constants import SUPPORTED_FORMATS_DISPLAY, SUPPORTED_TRANSCRIPT_EXTENSIONS


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation check.

    Attributes:
        is_valid: Whether the validation passed.
        error_type: Type of error if validation failed (e.g., "invalid_extension").
        error_message: Human-readable error description.
    """

    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None


def validate_transcript(file_path: str, content: str) -> ValidationResult:
    """Validate a transcript file.

    Checks that the file has a .md extension and contains non-empty content.

    Args:
        file_path: Path to the transcript file.
        content: Content of the transcript file.

    Returns:
        ValidationResult indicating success or failure with error details.
    """
    # Check file extension
    if not file_path.lower().endswith(SUPPORTED_TRANSCRIPT_EXTENSIONS):
        return ValidationResult(
            is_valid=False,
            error_type="invalid_extension",
            error_message=f"Transcript file must be {SUPPORTED_FORMATS_DISPLAY}",
        )

    # Check content is non-empty
    if not content or not content.strip():
        return ValidationResult(
            is_valid=False,
            error_type="empty_content",
            error_message="Transcript file cannot be empty",
        )

    return ValidationResult(is_valid=True)
