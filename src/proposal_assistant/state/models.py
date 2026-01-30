"""State models for Proposal Assistant thread management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class State(Enum):
    """Conversation state for a thread."""

    IDLE = "IDLE"
    WAITING_FOR_INPUTS = "WAITING_FOR_INPUTS"
    GENERATING_DEAL_ANALYSIS = "GENERATING_DEAL_ANALYSIS"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    GENERATING_DECK = "GENERATING_DECK"
    DONE = "DONE"
    ERROR = "ERROR"


class Event(Enum):
    """Events that trigger state transitions."""

    ANALYSE_REQUESTED = "ANALYSE_REQUESTED"
    INPUTS_MISSING = "INPUTS_MISSING"
    DEAL_ANALYSIS_CREATED = "DEAL_ANALYSIS_CREATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    UPDATED_DEAL_ANALYSIS_PROVIDED = "UPDATED_DEAL_ANALYSIS_PROVIDED"
    DECK_CREATED = "DECK_CREATED"
    FAILED = "FAILED"
    REGENERATE_REQUESTED = "REGENERATE_REQUESTED"
    CLOUD_CONSENT_GIVEN = "CLOUD_CONSENT_GIVEN"


@dataclass
class ThreadState:
    """Tracks the state and data for a single Slack thread conversation."""

    # Identifiers (required)
    thread_ts: str
    channel_id: str
    user_id: str

    # Identifiers (optional)
    channel_type: Optional[str] = None  # "im" for DMs, "channel" for public channels
    user_email: Optional[str] = None

    # Client info
    client_name: Optional[str] = None
    client_folder_id: Optional[str] = None
    analyse_folder_id: Optional[str] = None
    proposals_folder_id: Optional[str] = None

    # Document references
    deal_analysis_doc_id: Optional[str] = None
    deal_analysis_link: Optional[str] = None
    deal_analysis_content: Optional[dict[str, Any]] = None
    deal_analysis_version: int = 1
    slides_deck_id: Optional[str] = None
    slides_deck_link: Optional[str] = None

    # State machine
    state: State = State.IDLE
    previous_state: Optional[State] = None

    # Input tracking
    input_transcript_file_ids: list[str] = field(default_factory=list)
    input_transcript_content: list[str] = field(default_factory=list)
    input_reference_file_ids: list[str] = field(default_factory=list)
    input_urls: list[str] = field(default_factory=list)

    # Output tracking
    missing_info_items: list[str] = field(default_factory=list)

    # Error handling
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0

    # Cloud consent
    cloud_consent_given: bool = False

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
