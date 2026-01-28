# Technical Design Document: Proposal Assistant Slack Bot

**Version:** 1.0\
**Last Updated:** 2026-01-28\
**Author:** Duy Tran\
**Status:** Draft

---

## 1. Architecture Overview

### 1.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              PROPOSAL ASSISTANT                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │    Slack     │    │    State     │    │     LLM      │    │   Google     │  │
│  │   Module     │◄──►│   Machine    │◄──►│   Module     │    │   Suite      │  │
│  │              │    │              │    │              │    │              │  │
│  │ • handlers   │    │ • machine.py │    │ • client.py  │    │ ┌──────────┐ │  │
│  │ • messages   │    │ • storage.py │    │ • prompts/   │    │ │  Drive   │ │  │
│  │ • commands   │    │              │    │ • context    │    │ └──────────┘ │  │
│  └──────┬───────┘    └──────────────┘    └──────┬───────┘    │ ┌──────────┐ │  │
│         │                                        │            │ │  Docs    │ │  │
│         │                                        │            │ └──────────┘ │  │
│         │                                        │            │ ┌──────────┐ │  │
│         │                                        │            │ │  Slides  │ │  │
│         │                                        │            │ └──────────┘ │  │
│         │                                        │            └──────┬───────┘  │
│         │                                        │                   │          │
│  ┌──────▼────────────────────────────────────────▼───────────────────▼───────┐  │
│  │                           SHARED UTILITIES                                │  │
│  │     config.py  │  parsing.py  │  validation.py  │  web_fetch.py          │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                │                    │                    │
                ▼                    ▼                    ▼
┌───────────────────────┐ ┌───────────────────┐ ┌────────────────────────────────┐
│     Slack API         │ │   Ollama (Local)  │ │      Google Cloud APIs         │
│ • Events (Socket Mode)│ │ • qwen2.5:14b     │ │ • Drive API v3                 │
│ • Web API             │ │ • OpenAI-compat   │ │ • Docs API v1                  │
│ • Interactive         │ │   endpoint        │ │ • Slides API v1                │
└───────────────────────┘ └───────────────────┘ └────────────────────────────────┘
```

### 1.2 Technology Stack Decisions

| Layer | Technology | Rationale |
| --- | --- | --- |
| **Language** | Python 3.12 | Team familiarity, excellent SDK support for all integrations |
| **Package Manager** | uv | Fast, modern Python packaging with lockfile support |
| **Slack SDK** | slack-bolt &gt;=1.18.0 | Official Slack framework, handles Socket Mode natively |
| **Google APIs** | google-api-python-client &gt;=2.100.0 | Official Google SDK, service account support |
| **LLM Client** | openai &gt;=1.0.0 | OpenAI-compatible SDK works with Ollama's `/v1` endpoint |
| **LLM Backend** | Ollama + qwen2.5:14b | Local inference, privacy-preserving, no API costs |
| **Testing** | pytest, pytest-cov, pytest-asyncio | Industry standard, good coverage tooling |
| **Linting/Format** | ruff + black | Fast linting, consistent formatting |
| **Type Checking** | pyright | Strict type checking for reliability |
| **State Storage** | JSON files (MVP) | Simple, debuggable; upgrade path to SQLite/Redis |

### 1.3 Component Breakdown

```
src/proposal_assistant/
├── __init__.py
├── main.py                    # Entry point, Bolt app initialization
├── config.py                  # Environment variables, constants
│
├── slack/
│   ├── __init__.py
│   ├── handlers.py            # Message/event handlers (Analyse, Yes/No)
│   ├── commands.py            # Slash commands (future)
│   └── messages.py            # Message templates, block formatters
│
├── drive/
│   ├── __init__.py
│   ├── client.py              # Google Drive API wrapper
│   ├── folders.py             # Folder navigation/creation logic
│   └── permissions.py         # Sharing/access management
│
├── docs/
│   ├── __init__.py
│   ├── client.py              # Google Docs API wrapper
│   └── deal_analysis.py       # Deal Analysis document generation
│
├── slides/
│   ├── __init__.py
│   ├── client.py              # Google Slides API wrapper
│   └── proposal_deck.py       # Proposal Deck generation logic
│
├── llm/
│   ├── __init__.py
│   ├── client.py              # LLM API client (Ollama/OpenAI-compat)
│   ├── context_builder.py     # Assembles context from inputs
│   └── prompts/
│       ├── __init__.py
│       ├── system_sales_advisor.txt
│       ├── deal_analysis.py
│       └── proposal_deck.py
│
├── state/
│   ├── __init__.py
│   ├── machine.py             # State machine implementation
│   └── storage.py             # Thread state persistence (JSON)
│
├── web/
│   ├── __init__.py
│   └── fetcher.py             # URL content fetching
│
└── utils/
    ├── __init__.py
    ├── parsing.py             # Transcript/markdown parsing
    └── validation.py          # Input validation helpers
```

---

## 2. Design Details

### 2.1 Data Models / Database Schema

#### Thread State (Primary Storage)

```python
# src/proposal_assistant/state/models.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class State(Enum):
    IDLE = "IDLE"
    WAITING_FOR_INPUTS = "WAITING_FOR_INPUTS"
    GENERATING_DEAL_ANALYSIS = "GENERATING_DEAL_ANALYSIS"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    GENERATING_DECK = "GENERATING_DECK"
    DONE = "DONE"
    ERROR = "ERROR"

class Event(Enum):
    ANALYSE_REQUESTED = "ANALYSE_REQUESTED"
    INPUTS_MISSING = "INPUTS_MISSING"
    DEAL_ANALYSIS_CREATED = "DEAL_ANALYSIS_CREATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    UPDATED_DEAL_ANALYSIS_PROVIDED = "UPDATED_DEAL_ANALYSIS_PROVIDED"
    DECK_CREATED = "DECK_CREATED"
    FAILED = "FAILED"
    REGENERATE_REQUESTED = "REGENERATE_REQUESTED"

@dataclass
class ThreadState:
    # Identifiers
    thread_ts: str                              # Primary key
    channel_id: str
    user_id: str
    user_email: Optional[str] = None
    
    # Client info
    client_name: Optional[str] = None
    client_folder_id: Optional[str] = None
    analyse_folder_id: Optional[str] = None
    proposals_folder_id: Optional[str] = None
    
    # Document references
    deal_analysis_doc_id: Optional[str] = None
    deal_analysis_link: Optional[str] = None
    deal_analysis_version: int = 1
    slides_deck_id: Optional[str] = None
    slides_deck_link: Optional[str] = None
    
    # State machine
    state: State = State.IDLE
    previous_state: Optional[State] = None
    
    # Input tracking
    input_transcript_file_ids: list[str] = field(default_factory=list)
    input_reference_file_ids: list[str] = field(default_factory=list)
    input_urls: list[str] = field(default_factory=list)
    
    # Output tracking
    missing_info_items: list[str] = field(default_factory=list)
    
    # Error handling
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

#### Document Metadata

```python
@dataclass
class DocumentMetadata:
    doc_id: str
    doc_type: str  # "deal_analysis" | "proposal_deck"
    thread_ts: str
    client_name: str
    created_by_user_id: str
    created_at: datetime
    web_link: str
    version: int = 1
    word_count: Optional[int] = None    # For Deal Analysis
    slide_count: Optional[int] = None   # For Proposal Deck
```

#### JSON Storage Structure

```
data/
├── threads/
│   └── {channel_id}_{thread_ts}.json
└── documents/
    └── {doc_id}.json
```

### 2.2 API Design

#### Internal Module Interfaces

**DriveClient Interface**

```python
class DriveClient:
    def find_folder(self, parent_id: str, folder_name: str) -> str | None:
        """Find folder by name under parent. Returns folder_id or None."""
    
    def create_folder(self, parent_id: str, folder_name: str) -> str:
        """Create folder under parent. Returns new folder_id."""
    
    def get_or_create_client_folder(self, client_name: str) -> dict:
        """
        Ensures full client folder structure exists.
        Returns: {
            "client_folder_id": str,
            "meetings_folder_id": str,
            "analyse_folder_id": str,
            "proposals_folder_id": str,
            "references_folder_id": str
        }
        """
    
    def download_file(self, file_id: str) -> bytes:
        """Download file content by ID."""
    
    def share_file(self, file_id: str, email: str, role: str = "writer") -> None:
        """Share file with user email."""
```

**DocsClient Interface**

```python
class DocsClient:
    def create_document(self, title: str, folder_id: str) -> tuple[str, str]:
        """Create new Google Doc. Returns: (doc_id, web_view_link)"""
    
    def populate_deal_analysis(self, doc_id: str, content: DealAnalysisContent) -> None:
        """Populate Deal Analysis with structured content."""
```

**SlidesClient Interface**

```python
class SlidesClient:
    def duplicate_template(self, template_id: str, title: str, folder_id: str) -> tuple[str, str]:
        """Duplicate template. Returns: (presentation_id, web_view_link)"""
    
    def populate_proposal_deck(self, presentation_id: str, content: ProposalDeckContent) -> None:
        """Populate slides with mapped content from Deal Analysis."""
    
    def get_layout_by_name(self, presentation_id: str, layout_name: str) -> str:
        """Get layout object ID by name."""
```

**LLMClient Interface**

```python
class LLMClient:
    def generate_deal_analysis(
        self,
        transcript: str,
        references: list[str],
        web_content: list[str]
    ) -> LLMResponse:
        """
        Returns: {
            "content": DealAnalysisContent,
            "missing_info": list[str],
            "raw_response": str
        }
        """
    
    def generate_proposal_deck_content(
        self,
        deal_analysis: DealAnalysisContent
    ) -> ProposalDeckContent:
        """Generate slide content mapped from Deal Analysis."""
```

**StateMachine Interface**

```python
class StateMachine:
    def get_state(self, thread_ts: str, channel_id: str) -> ThreadState:
        """Get or create thread state."""
    
    def transition(self, thread_ts: str, event: Event, **kwargs) -> ThreadState:
        """Execute state transition based on event."""
    
    def can_transition(self, current_state: State, event: Event) -> bool:
        """Check if transition is valid."""
```

### 2.3 State Machine Transitions

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
┌──────┐  ANALYSE_REQUESTED   ┌─────────────────────┐        │
│ IDLE │─────────────────────►│ GENERATING_DEAL_    │        │
└──────┘  (with transcript)   │ ANALYSIS            │        │
    ▲                         └──────────┬──────────┘        │
    │                                    │                    │
    │  INPUTS_MISSING                    │ DEAL_ANALYSIS_    │
    │  (no transcript)                   │ CREATED           │
    │                                    ▼                    │
    │                         ┌─────────────────────┐        │
    │                         │ WAITING_FOR_        │        │
    │                         │ APPROVAL            │◄───────┤
    │                         └──────────┬──────────┘        │
    │                                    │                    │
    │         ┌──────────────────────────┼──────────────┐    │
    │         │                          │              │    │
    │         ▼                          ▼              │    │
    │    REJECTED              APPROVED / UPDATED_     │    │
    │    (user says No)        DEAL_ANALYSIS_PROVIDED  │    │
    │         │                          │              │    │
    │         ▼                          ▼              │    │
    │    ┌──────┐             ┌─────────────────────┐  │    │
    └────│ DONE │             │ GENERATING_DECK     │  │    │
         └──────┘             └──────────┬──────────┘  │    │
              ▲                          │             │    │
              │                          │ DECK_       │    │
              │                          │ CREATED     │    │
              │                          ▼             │    │
              └─────────────────────┬──────┐          │    │
                                    │ DONE │          │    │
                                    └──────┘          │    │
                                                      │    │
         ┌───────┐  FAILED (any state)               │    │
         │ ERROR │◄──────────────────────────────────┘    │
         └───┬───┘                                        │
             │                                            │
             │  RETRY (user action)                       │
             └────────────────────────────────────────────┘
```

### 2.4 Key Module Interactions (Sequence Diagram)

```
User          Slack           Handlers        StateMachine      LLM            Drive/Docs
 │              │                │                │              │                │
 │──"Analyse"──►│                │                │              │                │
 │  + file      │───message_event──►│             │              │                │
 │              │                │──get_state()──►│              │                │
 │              │                │◄──IDLE─────────│              │                │
 │              │                │                │              │                │
 │              │                │──validate_inputs()──────────────────────────────►│
 │              │                │◄──transcript_content────────────────────────────│
 │              │                │                │              │                │
 │              │                │──transition(ANALYSE_REQUESTED)►│              │
 │              │                │◄──GENERATING_DEAL_ANALYSIS────│              │
 │              │                │                │              │                │
 │              │◄──"Analyzing..."│               │              │                │
 │◄─────────────│                │                │              │                │
 │              │                │──generate_deal_analysis()───►│                │
 │              │                │◄──content + missing_info─────│                │
 │              │                │                │              │                │
 │              │                │──create_document()─────────────────────────────►│
 │              │                │◄──doc_id, link──────────────────────────────────│
 │              │                │                │              │                │
 │              │                │──transition(DEAL_ANALYSIS_CREATED)►│           │
 │              │                │◄──WAITING_FOR_APPROVAL────────│              │
 │              │                │                │              │                │
 │              │◄──"Deal Analysis created"       │              │                │
 │              │   + link + missing info         │              │                │
 │              │   + approval buttons            │              │                │
 │◄─────────────│                │                │              │                │
```

---

## 3. Core Features List

### 3.1 MVP Features (Dependency Order)

| Priority | Feature | Description | Dependencies |
| --- | --- | --- | --- |
| **P0** | **F1: Configuration & Environment** | Load env vars, validate config, initialize logging | None |
| **P0** | **F2: State Machine Core** | State enum, transitions, guards, persistence | F1 |
| **P0** | **F3: Slack Event Handling** | Receive messages, parse "Analyse", download files | F1 |
| **P0** | **F4: Input Validation** | Validate .md files, detect empty/invalid, language check | F3 |
| **P0** | **F5: Drive Folder Operations** | Find/create client folders, folder hierarchy | F1 |
| **P0** | **F6: LLM Context Builder** | Assemble transcript + references, token management | F4 |
| **P0** | **F7: LLM Client** | Connect to Ollama, retry logic, error handling | F1, F6 |
| **P0** | **F8: Deal Analysis Generation** | Generate structured content via LLM | F6, F7 |
| **P0** | **F9: Google Docs Integration** | Create doc, populate template, add footer | F5 |
| **P0** | **F10: Missing Info Detection** | Extract missing fields, format for Slack | F8 |
| **P0** | **F11: Slack Response Formatting** | Block messages, links, buttons, error messages | F3 |
| **P0** | **F12: Approval Gate** | Handle Yes/No buttons, state transitions | F2, F11 |
| **P0** | **F13: Proposal Deck Generation** | Map Deal Analysis → slides, populate template | F8, F5 |
| **P0** | **F14: Google Slides Integration** | Duplicate template, populate placeholders | F5 |
| **P0** | **F15: File Sharing/Permissions** | Share docs with user, channel members | F9, F14 |
| **P1** | **F16: Multi-file Support** | Merge multiple transcripts | F4, F6 |
| **P1** | **F17: Updated Deal Analysis Handling** | Accept user-edited doc for deck generation | F12, F13 |
| **P1** | **F18: Regeneration (Versioning)** | Create v2, v3 Deal Analysis versions | F8, F9 |
| **P1** | **F19: Web URL Fetching** | Fetch external URLs for context | F6 |
| **P1** | **F20: DM Support** | Full functionality in direct messages | F3, F15 |
| **P2** | **F21: Cloud LLM Fallback** | Consent-based OpenAI/Anthropic fallback | F7 |
| **P2** | **F22: Auto-chunking Long Transcripts** | Split &gt;32K tokens, summarize chunks | F6, F7 |
| **P3** | **F23: Analytics Dashboard** | Usage tracking, quality metrics | All |

### 3.2 Feature Dependency Graph

```
F1 (Config)
 ├── F2 (State Machine)
 │    └── F12 (Approval Gate)
 │         ├── F17 (Updated Doc Handling)
 │         └── F13 (Deck Generation)
 │              └── F14 (Slides Integration)
 │                   └── F15 (Permissions)
 ├── F3 (Slack Events)
 │    ├── F4 (Input Validation)
 │    │    ├── F6 (Context Builder)
 │    │    │    ├── F7 (LLM Client)
 │    │    │    │    ├── F8 (Deal Analysis Gen)
 │    │    │    │    │    ├── F9 (Docs Integration)
 │    │    │    │    │    └── F10 (Missing Info)
 │    │    │    │    ├── F21 (Cloud Fallback)
 │    │    │    │    └── F22 (Auto-chunking)
 │    │    │    └── F19 (Web Fetching)
 │    │    └── F16 (Multi-file)
 │    ├── F11 (Slack Formatting)
 │    └── F20 (DM Support)
 └── F5 (Drive Folders)
      └── F15 (Permissions)
```

---

## 4. Implementation Plan

### Phase 1: Foundation (Week 1)

#### 4.1.1 Implement F1: Configuration & Environment

**Files to create:**

- `src/proposal_assistant/config.py`
- `.env.example`
- `pyproject.toml`

**Complexity:** Small

```python
# Key implementation details
@dataclass
class Config:
    # Slack
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str
    
    # Google
    google_service_account_json: str
    google_drive_root_folder_id: str
    
    # LLM
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:14b"
    ollama_num_ctx: int = 32768
    
    # Templates
    proposal_template_slide_id: str
    
    # App
    log_level: str = "INFO"
    environment: str = "development"
```

#### 4.1.2 Write tests for F1

**Files to create:**

- `tests/unit/test_config.py`

**Test cases:**

- Load valid config from env
- Missing required var raises error
- Default values applied correctly

---

#### 4.1.3 Implement F2: State Machine Core

**Files to create:**

- `src/proposal_assistant/state/models.py`
- `src/proposal_assistant/state/machine.py`
- `src/proposal_assistant/state/storage.py`

**Complexity:** Medium

```python
# Key transition rules
TRANSITIONS = {
    (State.IDLE, Event.ANALYSE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
    (State.IDLE, Event.INPUTS_MISSING): State.WAITING_FOR_INPUTS,
    (State.GENERATING_DEAL_ANALYSIS, Event.DEAL_ANALYSIS_CREATED): State.WAITING_FOR_APPROVAL,
    (State.GENERATING_DEAL_ANALYSIS, Event.FAILED): State.ERROR,
    (State.WAITING_FOR_APPROVAL, Event.APPROVED): State.GENERATING_DECK,
    (State.WAITING_FOR_APPROVAL, Event.REJECTED): State.DONE,
    (State.WAITING_FOR_APPROVAL, Event.UPDATED_DEAL_ANALYSIS_PROVIDED): State.GENERATING_DECK,
    (State.WAITING_FOR_APPROVAL, Event.REGENERATE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
    (State.GENERATING_DECK, Event.DECK_CREATED): State.DONE,
    (State.GENERATING_DECK, Event.FAILED): State.ERROR,
    (State.ERROR, Event.ANALYSE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
}
```

#### 4.1.4 Write tests for F2

**Files to create:**

- `tests/unit/test_state_machine.py`
- `tests/unit/test_state_storage.py`

**Test cases:**

- Valid transitions (all paths)
- Invalid transitions rejected
- State persistence (save/load)
- Thread state recovery after restart

---

#### 4.1.5 Implement F3: Slack Event Handling

**Files to create:**

- `src/proposal_assistant/main.py`
- `src/proposal_assistant/slack/__init__.py`
- `src/proposal_assistant/slack/handlers.py`

**Complexity:** Medium

```python
# Key handlers
@app.message(re.compile(r"(?i)^analyse$|^analyze$"))
def handle_analyse_command(message, say, client):
    """Handle 'Analyse' command with file attachments."""

@app.action("approve_deck")
def handle_approval(ack, body, say):
    """Handle Yes button click."""

@app.action("reject_deck")
def handle_rejection(ack, body, say):
    """Handle No button click."""
```

#### 4.1.6 Write tests for F3

**Files to create:**

- `tests/unit/test_slack_handlers.py`
- `tests/fixtures/slack_events/message_with_file.json`
- `tests/fixtures/slack_events/approval_yes.json`

**Test cases:**

- Parse "Analyse" command
- Extract file attachments
- Download file via url_private_download
- Handle messages in threads vs new messages

---

#### 4.1.7 Implement F4: Input Validation

**Files to create:**

- `src/proposal_assistant/utils/validation.py`
- `src/proposal_assistant/utils/parsing.py`

**Complexity:** Small

```python
def validate_transcript(content: bytes, filename: str) -> ValidationResult:
    """
    Validates transcript file.
    Checks: non-empty, valid markdown, English language.
    """

def extract_client_name(filename: str, content: str) -> str | None:
    """Extract client name from filename or content."""
```

#### 4.1.8 Write tests for F4

**Files to create:**

- `tests/unit/test_validation.py`
- `tests/unit/test_parsing.py`
- `tests/fixtures/transcripts/valid_transcript.md`
- `tests/fixtures/transcripts/empty_transcript.md`

**Test cases:**

- Valid .md file accepted
- Empty file rejected with correct error
- Non-English transcript rejected
- Client name extraction patterns

---

### Phase 2: Core Integration (Week 2)

#### 4.2.1 Implement F5: Drive Folder Operations

**Files to create:**

- `src/proposal_assistant/drive/__init__.py`
- `src/proposal_assistant/drive/client.py`
- `src/proposal_assistant/drive/folders.py`

**Complexity:** Medium

#### 4.2.2 Write tests for F5

**Files to create:**

- `tests/unit/test_drive_folders.py`
- `tests/integration/test_drive_client.py`

---

#### 4.2.3 Implement F6: LLM Context Builder

**Files to create:**

- `src/proposal_assistant/llm/__init__.py`
- `src/proposal_assistant/llm/context_builder.py`

**Complexity:** Medium

```python
class ContextBuilder:
    MAX_TRANSCRIPT_TOKENS = 24000
    MAX_REFERENCES_TOKENS = 10000
    MAX_WEB_TOKENS = 6000
    RESERVED_OUTPUT_TOKENS = 8000
    
    def build_context(
        self,
        transcript: str,
        references: list[str],
        web_content: list[str]
    ) -> str:
        """Assemble context within token limits."""
```

#### 4.2.4 Write tests for F6

**Files to create:**

- `tests/unit/test_context_builder.py`

---

#### 4.2.5 Implement F7: LLM Client

**Files to create:**

- `src/proposal_assistant/llm/client.py`
- `src/proposal_assistant/llm/prompts/system_sales_advisor.txt`
- `src/proposal_assistant/llm/prompts/deal_analysis.py`

**Complexity:** Medium

```python
class LLMClient:
    MAX_RETRIES = 3
    BACKOFF_SECONDS = [1, 2, 4]
    
    async def _call_with_retry(self, messages: list[dict]) -> str:
        """Call LLM with exponential backoff retry."""
```

#### 4.2.6 Write tests for F7

**Files to create:**

- `tests/unit/test_llm_client.py`
- `tests/fixtures/llm_responses/deal_analysis_response.json`

---

#### 4.2.7 Implement F8: Deal Analysis Generation

**Files to create:**

- `src/proposal_assistant/llm/prompts/deal_analysis.py` (templates)
- Extend `src/proposal_assistant/llm/client.py`

**Complexity:** Large

#### 4.2.8 Write tests for F8

**Files to create:**

- `tests/unit/test_deal_analysis_generation.py`

---

### Phase 3: Document Creation (Week 3)

#### 4.3.1 Implement F9: Google Docs Integration

**Files to create:**

- `src/proposal_assistant/docs/__init__.py`
- `src/proposal_assistant/docs/client.py`
- `src/proposal_assistant/docs/deal_analysis.py`

**Complexity:** Large

#### 4.3.2 Write tests for F9

**Files to create:**

- `tests/unit/test_docs_client.py`
- `tests/integration/test_docs_creation.py`

---

#### 4.3.3 Implement F10: Missing Info Detection

**Files to create:**

- `src/proposal_assistant/llm/prompts/missing_info_detector.txt`
- Extend LLM client

**Complexity:** Small

#### 4.3.4 Write tests for F10

**Files to create:**

- `tests/unit/test_missing_info.py`

---

#### 4.3.5 Implement F11: Slack Response Formatting

**Files to create:**

- `src/proposal_assistant/slack/messages.py`

**Complexity:** Medium

```python
def format_deal_analysis_complete(
    doc_link: str,
    missing_items: list[str]
) -> list[dict]:
    """Format Deal Analysis complete message with blocks."""

def format_approval_buttons() -> list[dict]:
    """Create Yes/No interactive buttons."""

def format_error_message(error_type: str, user_message: str) -> list[dict]:
    """Format user-friendly error message."""
```

#### 4.3.6 Write tests for F11

**Files to create:**

- `tests/unit/test_slack_messages.py`

---

#### 4.3.7 Implement F12: Approval Gate

**Files to create:**

- Extend `src/proposal_assistant/slack/handlers.py`

**Complexity:** Small

#### 4.3.8 Write tests for F12

**Files to create:**

- `tests/unit/test_approval_handler.py`

---

### Phase 4: Proposal Deck (Week 4)

#### 4.4.1 Implement F13: Proposal Deck Generation

**Files to create:**

- `src/proposal_assistant/llm/prompts/proposal_deck.py`
- Extend LLM client

**Complexity:** Large

#### 4.4.2 Write tests for F13

**Files to create:**

- `tests/unit/test_proposal_deck_generation.py`
- `tests/fixtures/llm_responses/proposal_deck_response.json`

---

#### 4.4.3 Implement F14: Google Slides Integration

**Files to create:**

- `src/proposal_assistant/slides/__init__.py`
- `src/proposal_assistant/slides/client.py`
- `src/proposal_assistant/slides/proposal_deck.py`
- `config/proposal_template_spec.json`

**Complexity:** Large

```python
SLIDE_LAYOUTS = {
    1: "TITLE",
    2: "TITLE_AND_BODY",
    3: "TITLE_AND_TWO_COLUMNS",
    4: "TITLE_AND_BODY",
    5: "SECTION_TITLE_AND_DESCRIPTION",
    6: "TITLE_AND_BODY",
    7: "TITLE_AND_TWO_COLUMNS",
    8: "BIG_NUMBER",
    9: "TITLE_AND_BODY",
    10: "TITLE_AND_TWO_COLUMNS",
    11: "TITLE_AND_BODY",
    12: "TITLE_AND_BODY",
}
```

#### 4.4.4 Write tests for F14

**Files to create:**

- `tests/unit/test_slides_client.py`
- `tests/unit/test_proposal_deck.py`
- `tests/integration/test_slides_creation.py`

---

#### 4.4.5 Implement F15: File Sharing/Permissions

**Files to create:**

- `src/proposal_assistant/drive/permissions.py`

**Complexity:** Small

#### 4.4.6 Write tests for F15

**Files to create:**

- `tests/unit/test_permissions.py`

---

### Phase 5: Enhanced Features (Week 5)

#### 4.5.1 Implement F16: Multi-file Support

**Complexity:** Small\
**Files:** Extend `handlers.py`, `context_builder.py`

#### 4.5.2 Write tests for F16

---

#### 4.5.3 Implement F17: Updated Deal Analysis Handling

**Complexity:** Medium\
**Files:** Extend `handlers.py`, add doc parsing

#### 4.5.4 Write tests for F17

---

#### 4.5.5 Implement F18: Regeneration (Versioning)

**Complexity:** Medium\
**Files:** Extend state models, handlers, docs client

#### 4.5.6 Write tests for F18

---

#### 4.5.7 Implement F19: Web URL Fetching

**Files to create:**

- `src/proposal_assistant/web/__init__.py`
- `src/proposal_assistant/web/fetcher.py`

**Complexity:** Small

#### 4.5.8 Write tests for F19

---

#### 4.5.9 Implement F20: DM Support

**Complexity:** Small\
**Files:** Extend handlers, permissions

#### 4.5.10 Write tests for F20

---

### Phase 6: Robustness & Polish (Week 6)

#### 4.6.1 Implement F21: Cloud LLM Fallback

**Complexity:** Medium\
**Files:** Extend LLM client, add consent flow

#### 4.6.2 Write tests for F21

---

#### 4.6.3 Implement F22: Auto-chunking Long Transcripts

**Complexity:** Medium\
**Files:** Extend context builder

#### 4.6.4 Write tests for F22

---

#### 4.6.5 End-to-End Integration Testing

**Files to create:**

- `tests/e2e/test_full_flow.py`
- `tests/e2e/test_error_recovery.py`

---

## 5. Testing Strategy

### 5.1 Unit Test Approach

**Coverage Target:** &gt;80% for core modules

**Key Principles:**

- Test each module in isolation
- Mock all external dependencies (Slack API, Google APIs, Ollama)
- Use fixtures for consistent test data
- Test both happy path and error cases

**Test File Naming:**

```
tests/unit/test_{module_name}.py
```

**Example Structure:**

```python
# tests/unit/test_state_machine.py
import pytest
from proposal_assistant.state.machine import StateMachine
from proposal_assistant.state.models import State, Event

class TestStateMachine:
    def test_valid_transition_idle_to_generating(self):
        """Valid: IDLE → GENERATING_DEAL_ANALYSIS"""
        
    def test_invalid_transition_idle_to_deck(self):
        """Invalid: IDLE → GENERATING_DECK (should raise)"""
        
    def test_approval_gate_enforced(self):
        """Cannot enter GENERATING_DECK without approval"""
```

### 5.2 Integration Test Approach

**Focus:** Component interactions with mocked external services

**Test Scenarios:**

| Scenario | Components | Verification |
| --- | --- | --- |
| Slack → State | Handlers + Machine | State transitions correctly |
| State → Drive | Machine + Drive client | Folders created with structure |
| LLM → Docs | LLM client + Docs client | Doc created with correct content |
| Full Deal Analysis | All (mocked LLM) | Doc created, link returned, state correct |
| Full Deck | All (mocked LLM) | Deck created from template, state = DONE |

**Mocking Strategy:**

```python
# Use pytest fixtures for mocks
@pytest.fixture
def mock_slack_client():
    with mock.patch('slack_sdk.WebClient') as mock_client:
        yield mock_client

@pytest.fixture
def mock_drive_service():
    with mock.patch('googleapiclient.discovery.build') as mock_build:
        yield mock_build
```

### 5.3 End-to-End Test Approach

**Environment:** Test Slack channel + test Drive folders

| Scenario | Steps | Expected |
| --- | --- | --- |
| Happy path | Attach transcript → "Analyse" → "Yes" | Both docs created |
| Rejection | Attach transcript → "Analyse" → "No" | Only Deal Analysis |
| Missing transcript | "Analyse" (no file) | Error, stays IDLE |
| LLM timeout | Simulate timeout | Retries 3x, then ERROR |
| Recovery | ERROR → retry | Successful completion |

### 5.4 Test File Naming Conventions

```
tests/
├── unit/
│   ├── test_config.py
│   ├── test_state_machine.py
│   ├── test_state_storage.py
│   ├── test_validation.py
│   ├── test_parsing.py
│   ├── test_llm_client.py
│   ├── test_context_builder.py
│   ├── test_drive_folders.py
│   ├── test_docs_client.py
│   ├── test_slides_client.py
│   └── test_slack_messages.py
├── integration/
│   ├── test_slack_to_state.py
│   ├── test_state_to_drive.py
│   ├── test_llm_to_docs.py
│   └── test_full_deal_analysis.py
├── e2e/
│   ├── test_happy_path.py
│   ├── test_rejection_flow.py
│   ├── test_error_recovery.py
│   └── test_edge_cases.py
└── fixtures/
    ├── transcripts/
    │   ├── valid_transcript.md
    │   ├── empty_transcript.md
    │   └── long_transcript.md
    ├── llm_responses/
    │   ├── deal_analysis_response.json
    │   └── proposal_deck_response.json
    └── slack_events/
        ├── message_with_file.json
        ├── approval_yes.json
        └── approval_no.json
```

### 5.5 Test Commands

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/proposal_assistant --cov-report=html

# Run specific module
uv run pytest tests/unit/test_state_machine.py

# Run integration tests
uv run pytest tests/integration/ -v

# Run e2e tests (requires test environment)
uv run pytest tests/e2e/ -v --env=test
```

---

## 6. Task Breakdown

### Epic 1: Project Setup & Configuration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T1.1 | Initialize repo with uv, pyproject.toml | 2h | \- |
| T1.2 | Create src/ package structure | 1h | T1.1 |
| T1.3 | Implement [config.py](http://config.py) with env var loading | 3h | T1.2 |
| T1.4 | Create .env.example with all variables | 1h | T1.3 |
| T1.5 | Set up pytest, ruff, black, pyright | 2h | T1.1 |
| T1.6 | Write unit tests for config | 2h | T1.3 |
| T1.7 | Create test fixtures directory structure | 1h | T1.5 |

### Epic 2: State Machine

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T2.1 | Define State and Event enums | 1h | T1.3 |
| T2.2 | Implement ThreadState dataclass | 2h | T2.1 |
| T2.3 | Implement StateMachine with transitions | 4h | T2.2 |
| T2.4 | Implement JSON storage backend | 3h | T2.2 |
| T2.5 | Add state recovery logic | 2h | T2.4 |
| T2.6 | Write unit tests for state machine | 4h | T2.3 |
| T2.7 | Write unit tests for storage | 3h | T2.4 |

### Epic 3: Slack Integration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T3.1 | Set up Bolt app in [main.py](http://main.py) | 2h | T1.3 |
| T3.2 | Implement "Analyse" message handler | 4h | T3.1, T2.3 |
| T3.3 | Implement file download from Slack | 3h | T3.2 |
| T3.4 | Implement approval button handlers | 3h | T3.2 |
| T3.5 | Create message formatting utilities | 4h | T3.1 |
| T3.6 | Implement error message templates | 2h | T3.5 |
| T3.7 | Write unit tests for handlers | 4h | T3.2 |
| T3.8 | Write unit tests for messages | 3h | T3.5 |
| T3.9 | Create Slack event fixtures | 2h | T1.7 |

### Epic 4: Input Validation

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T4.1 | Implement transcript validation | 3h | T3.3 |
| T4.2 | Implement client name extraction | 2h | T4.1 |
| T4.3 | Implement language detection | 3h | T4.1 |
| T4.4 | Write unit tests for validation | 3h | T4.1 |
| T4.5 | Create transcript fixtures | 2h | T1.7 |

### Epic 5: Google Drive Integration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T5.1 | Implement DriveClient with auth | 4h | T1.3 |
| T5.2 | Implement folder search/create | 3h | T5.1 |
| T5.3 | Implement get_or_create_client_folder | 3h | T5.2 |
| T5.4 | Implement file download | 2h | T5.1 |
| T5.5 | Implement file sharing | 3h | T5.1 |
| T5.6 | Write unit tests for Drive client | 4h | T5.1 |
| T5.7 | Write integration tests for Drive | 4h | T5.3 |

### Epic 6: LLM Integration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T6.1 | Implement LLMClient with Ollama connection | 4h | T1.3 |
| T6.2 | Implement retry with exponential backoff | 3h | T6.1 |
| T6.3 | Implement context builder with token mgmt | 5h | T6.1 |
| T6.4 | Create system sales advisor prompt | 3h | T6.1 |
| T6.5 | Create Deal Analysis generation prompt | 4h | T6.4 |
| T6.6 | Implement generate_deal_analysis() | 5h | T6.3, T6.5 |
| T6.7 | Implement missing info detection | 3h | T6.6 |
| T6.8 | Write unit tests for LLM client | 4h | T6.1 |
| T6.9 | Write unit tests for context builder | 3h | T6.3 |
| T6.10 | Create LLM response fixtures | 2h | T1.7 |

### Epic 7: Google Docs Integration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T7.1 | Implement DocsClient with auth | 3h | T1.3 |
| T7.2 | Implement document creation | 3h | T7.1 |
| T7.3 | Implement Deal Analysis template | 5h | T7.2 |
| T7.4 | Add footer disclaimer | 1h | T7.3 |
| T7.5 | Add missing info formatting (bold/red) | 2h | T7.3 |
| T7.6 | Write unit tests for Docs client | 3h | T7.1 |
| T7.7 | Write integration tests for Docs | 4h | T7.3 |

### Epic 8: Google Slides Integration

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T8.1 | Implement SlidesClient with auth | 3h | T1.3 |
| T8.2 | Implement template duplication | 3h | T8.1 |
| T8.3 | Implement get_layout_by_name() | 2h | T8.2 |
| T8.4 | Create proposal_template_spec.json | 2h | \- |
| T8.5 | Implement placeholder population | 5h | T8.3, T8.4 |
| T8.6 | Implement slide content overflow handling | 4h | T8.5 |
| T8.7 | Create Proposal Deck generation prompt | 4h | T6.4 |
| T8.8 | Implement generate_proposal_deck_content() | 5h | T6.3, T8.7 |
| T8.9 | Write unit tests for Slides client | 4h | T8.1 |
| T8.10 | Write integration tests for Slides | 4h | T8.5 |

### Epic 9: End-to-End Flow

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T9.1 | Integrate all components in handlers | 6h | All Epics 1-8 |
| T9.2 | Implement full Deal Analysis flow | 4h | T9.1 |
| T9.3 | Implement full Proposal Deck flow | 4h | T9.2 |
| T9.4 | Write E2E happy path test | 4h | T9.3 |
| T9.5 | Write E2E error recovery test | 3h | T9.4 |

### Epic 10: Enhanced Features (P1)

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T10.1 | Implement multi-file transcript support | 4h | T9.3 |
| T10.2 | Implement updated Deal Analysis handling | 5h | T9.3 |
| T10.3 | Implement regeneration with versioning | 5h | T9.3 |
| T10.4 | Implement web URL fetching | 4h | T6.3 |
| T10.5 | Implement DM support | 3h | T9.3 |
| T10.6 | Write tests for enhanced features | 6h | T10.1-T10.5 |

### Epic 11: Robustness (P2)

| Task ID | Task | Estimate | Dependencies |
| --- | --- | --- | --- |
| T11.1 | Implement cloud LLM fallback with consent | 5h | T6.1 |
| T11.2 | Implement auto-chunking for long transcripts | 5h | T6.3 |
| T11.3 | Write tests for robustness features | 4h | T11.1-T11.2 |

### Summary: Total Estimated Hours

| Epic | Hours |
| --- | --- |
| Epic 1: Setup | 12h |
| Epic 2: State Machine | 19h |
| Epic 3: Slack Integration | 27h |
| Epic 4: Input Validation | 13h |
| Epic 5: Drive Integration | 23h |
| Epic 6: LLM Integration | 36h |
| Epic 7: Docs Integration | 21h |
| Epic 8: Slides Integration | 36h |
| Epic 9: E2E Flow | 21h |
| Epic 10: Enhanced Features | 27h |
| Epic 11: Robustness | 14h |
| **Total** | **\~249h** |

**Recommended Sprint Breakdown:**

- Week 1-2: Epics 1-4 (Foundation) - \~71h
- Week 3: Epics 5-6 (Integrations) - \~59h
- Week 4: Epics 7-8 (Documents) - \~57h
- Week 5: Epic 9 (E2E) - \~21h
- Week 6: Epics 10-11 (Polish) - \~41h

---

## Appendix A: Error Handling Reference

| Error Code | Trigger | User Message | Recovery |
| --- | --- | --- | --- |
| INPUT_MISSING | No transcript | "Please attach a meeting transcript (.md file)" | User retries |
| INPUT_INVALID | Empty transcript | "Transcript file appears empty or invalid" | User retries |
| LANGUAGE_UNSUPPORTED | Non-English | "Only English transcripts supported" | User provides English |
| DRIVE_PERMISSION | Folder inaccessible | "Unable to access client folder" | Admin fix |
| DRIVE_QUOTA | API quota exceeded | "Drive temporarily unavailable" | Auto-retry |
| DOCS_ERROR | Doc creation failed | "Failed to create Deal Analysis" | Auto-retry |
| SLIDES_ERROR | Deck creation failed | "Failed to create proposal deck" | Auto-retry |
| LLM_ERROR | Ollama error | "AI service temporarily unavailable" | Auto-retry (3x) |
| LLM_INVALID | Invalid LLM response | "Unable to generate analysis" | User retries |
| LLM_OFFLINE | Ollama down | "Local AI unavailable. Use cloud?" | User consent |
| APPROVAL_UNCLEAR | Unknown response | "Please reply 'Yes' or 'No'" | Wait for clear response |
| STATE_MISSING | Thread state lost | "Lost track. Please start over" | User restarts |

---

## Appendix B: Environment Variables

```bash
# Required - Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...

# Required - Google
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
GOOGLE_DRIVE_ROOT_FOLDER_ID=1ABC...

# Required - LLM
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:14b

# Required - Templates
PROPOSAL_TEMPLATE_SLIDE_ID=1XYZ...

# Optional
OLLAMA_NUM_CTX=32768
LOG_LEVEL=INFO
ENVIRONMENT=development
```