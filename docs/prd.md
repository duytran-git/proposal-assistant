# Product Requirements Document: Proposal Assistant Slack Bot

**Version:** 1.1
**Last Updated:** 2026-01-28
**Status:** Draft (Updated with stakeholder interview decisions)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals & Success Metrics](#2-goals--success-metrics)
3. [User Stories with Acceptance Criteria](#3-user-stories-with-acceptance-criteria)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [API Contracts](#6-api-contracts)
7. [Data Models](#7-data-models)
8. [Error Handling Matrix](#8-error-handling-matrix)
9. [Security & Compliance Requirements](#9-security--compliance-requirements)
10. [Dependencies & External Services](#10-dependencies--external-services)
11. [Testing Strategy](#11-testing-strategy)
12. [Rollout Plan](#12-rollout-plan)
13. [Appendix A: Proposal Template Specification](#appendix-a-proposal-template-specification)

---

## 1. Executive Summary

**Project:** Proposal Assistant Slack Bot
**Stakeholders:** Renessai consultants and salespeople
**Target Completion:** 6 weeks from Phase 1 start

Proposal Assistant is a Slack bot that transforms client discovery inputs into structured draft outputs for the Renessai sales team. The bot implements a two-step workflow: first generating a Deal Analysis document (Google Doc) from meeting transcripts and reference materials, then creating a Proposal Deck (Google Slides) following explicit human approval.

The system prioritizes grounded content over speculation—preferring client language from transcripts and flagging missing information rather than inventing details. All outputs are drafts designed for human review and editing. The approval gate between Deal Analysis and Proposal Deck creation ensures quality control and allows users to refine the analysis before proceeding.

The bot integrates with Slack for user interaction, Google Drive for file storage and organization, Google Docs for Deal Analysis creation, Google Slides for Proposal Deck generation, and Ollama (with Qwen2.5:14b) for LLM-powered content generation.

---

## 2. Goals & Success Metrics

(Source: Section 18)

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Time to first Deal Analysis draft | < 5 minutes | Timestamp: message received → doc link sent |
| Time to Proposal Deck draft | < 3 minutes | Timestamp: approval received → deck link sent |
| User adoption rate | 80% of new proposals use the bot within 3 months | Count proposals created via bot vs manual |
| Draft quality score | > 4/5 average rating | Post-generation survey (optional Slack reaction) |
| Missing info accuracy | 90%+ of flagged items are genuinely missing | Spot-check audits by sales leads |
| Error rate | < 5% of requests result in ERROR state | Logging and monitoring |
| User retry rate | < 10% of users need to retry due to bot errors | Track FAILED → retry sequences |

---

## 3. User Stories with Acceptance Criteria

### US-001: Initiate Deal Analysis

**As a** consultant, **I want to** start an analysis by attaching a transcript and saying "Analyse" **so that** I can quickly generate a structured Deal Analysis document.

**Acceptance Criteria:**
1. Bot acknowledges receipt within 3 seconds of message
2. Bot accepts .md transcript files attached to the message
3. Bot extracts client name from transcript filename or content
4. Bot creates Deal Analysis in the correct Drive folder (`/Clients/{ClientName}/Analyse here/`)
5. Bot replies in thread with a link to the created document

### US-002: Review Missing Information

**As a** salesperson, **I want to** see clearly listed missing information **so that** I know what follow-up questions to ask the client.

**Acceptance Criteria:**
1. Bot identifies missing fields from the Deal Analysis template
2. Missing items are listed clearly in the Slack message (bulleted list)
3. Missing items include category (e.g., "Budget range", "Decision timeline")
4. Bot labels uncertain areas as "Unknown / Not provided" in the document
5. Bot never invents budgets, timelines, stakeholder names, or metrics

### US-003: Approve Deck Creation

**As a** consultant, **I want to** approve or reject deck creation after reviewing the Deal Analysis **so that** I maintain control over the process.

**Acceptance Criteria:**
1. Bot explicitly asks "Should I continue and create a draft proposal deck?"
2. Bot accepts "Yes" as approval to proceed
3. Bot accepts "No" as rejection and stops gracefully
4. Bot does not create deck without explicit approval
5. Bot confirms receipt of approval before starting deck generation

### US-004: Use Updated Deal Analysis

**As a** salesperson, **I want to** provide an updated Deal Analysis **so that** the deck reflects my manual corrections.

**Acceptance Criteria:**
1. Bot accepts attached document files after initial Deal Analysis creation
2. Bot uses the updated document for deck generation instead of the original
3. Bot confirms it received and will use the updated analysis
4. Deck content reflects changes from the updated document

### US-005: Decline Deck Creation

**As a** consultant, **I want to** decline deck creation and still have my Deal Analysis saved **so that** I can use it for other purposes.

**Acceptance Criteria:**
1. Replying "No" stops the workflow gracefully
2. Deal Analysis document remains accessible in Drive
3. Bot acknowledges the decision with a friendly message
4. Bot offers to create a deck later if needed

### US-006: Receive Document Links

**As a** user, **I want to** receive direct links to created documents **so that** I can access them immediately.

**Acceptance Criteria:**
1. All created documents include shareable Google Drive links
2. Links are clickable in Slack messages
3. User has Editor access to created documents
4. Links are sent in the same thread as the original request

### US-007: Regenerate Deal Analysis

**As a** consultant, **I want to** regenerate the Deal Analysis if I'm unsatisfied with the first version **so that** I can get a better draft without starting over.

**Acceptance Criteria:**
1. User can request regeneration in the same thread
2. Bot creates "Deal Analysis v2" as a new document
3. Original version (v1) remains accessible for reference
4. Version number is included in document title
5. Bot confirms which version is being used for deck generation

### US-008: Use Bot in Direct Messages

**As a** user, **I want to** use the bot in a DM for private workflows **so that** I can work on sensitive deals without team visibility.

**Acceptance Criteria:**
1. Bot functions identically in DMs and channels
2. Documents are shared only with the requesting user
3. No difference in features or capabilities between DM and channel usage
4. State tracking works the same in DM threads

### US-009: Handle Multiple Transcripts

**As a** consultant, **I want to** attach multiple transcript files in a single request **so that** I can analyze a series of meetings together.

**Acceptance Criteria:**
1. Bot accepts multiple .md file attachments in one message
2. Content from all transcripts is merged into a single analysis
3. Bot indicates how many files were processed
4. Missing information is aggregated across all transcripts
5. Output is a single unified Deal Analysis document

### US-010: Cloud LLM Fallback

**As a** user, **I want** the bot to offer a cloud LLM option when the local server is unavailable **so that** I can still complete my work.

**Acceptance Criteria:**
1. Bot detects when local Ollama is unavailable
2. Bot asks user for consent before using cloud API
3. User can decline and wait for local service
4. If consented, bot proceeds with cloud LLM (OpenAI/Anthropic)
5. No data is sent to cloud without explicit user approval

---

## 4. Functional Requirements

### 4.1 Slack Module

(Source: Sections 11, 20.1, 20.2)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-SLACK-001 | Receive message events | Accept message events with file attachments via Slack API |
| FR-SLACK-002 | Parse commands | Detect "Analyse" command from message text |
| FR-SLACK-003 | Thread replies | Reply in the same thread with document links and status |
| FR-SLACK-004 | File download | Download attached files via `url_private_download` |
| FR-SLACK-005 | Approval detection | Detect approval responses ("Yes"/"No") in thread |
| FR-SLACK-006 | Rich formatting | Format messages with blocks (mrkdwn) for readability |
| FR-SLACK-007 | User lookup | Retrieve user email via `users.info` API for Drive sharing |
| FR-SLACK-008 | Acknowledgment | Send acknowledgment within 3 seconds of receiving message |
| FR-SLACK-009 | Button-based approval | Use Slack interactive buttons (Yes/No) instead of text for approval |
| FR-SLACK-010 | Language detection | Detect transcript language; reject non-English with clear error message |
| FR-SLACK-011 | Regeneration support | Accept "Regenerate" command to create versioned Deal Analysis (v2, v3, etc.) |
| FR-SLACK-012 | DM support | Full functionality in direct messages identical to channels |
| FR-SLACK-013 | Multi-file handling | Accept and merge multiple .md transcript files in single request |

### 4.2 Drive Module

(Source: Sections 11, 13, 20.3)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-DRIVE-001 | Folder search | Find folder by name under a parent folder |
| FR-DRIVE-002 | Folder creation | Create folder structure for new clients |
| FR-DRIVE-003 | Client folder resolution | Get or create full client folder hierarchy |
| FR-DRIVE-004 | File download | Download file content by ID |
| FR-DRIVE-005 | File sharing | Share file with user email as Editor |
| FR-DRIVE-006 | Service account | Use service account for all operations |
| FR-DRIVE-007 | Channel sharing | Share with all members of the Slack channel where bot was invoked |
| FR-DRIVE-008 | Case study lookup | Search case studies by industry keyword match from Deal Analysis |

**Required Folder Structure:**
```
Google Drive/
└── Clients/
    └── {ClientName}/
        ├── Meetings/           # Input: transcripts
        ├── Analyse here/       # Output: Deal Analysis docs
        ├── Proposals/          # Output: Proposal decks
        └── References/         # Optional: reference materials
```

### 4.3 Docs Module

(Source: Sections 8, 20.4)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-DOCS-001 | Document creation | Create new Google Doc in specified folder |
| FR-DOCS-002 | Template population | Populate Deal Analysis with exact template structure |
| FR-DOCS-003 | Link return | Return doc_id and web_view_link after creation |
| FR-DOCS-004 | Footer disclaimer | Add footer: "Draft generated by Proposal Assistant. Review before use." |
| FR-DOCS-005 | Prominent warnings | Display missing info with bold/red sections and top-of-doc summary |
| FR-DOCS-006 | Version linking | Include version number in title; link versions (v1 → v2) in metadata |

**Deal Analysis Template Structure:**

1. **Opportunity Snapshot** (table format)
   - Company, Industry/Segment, Size, Contact(s), Opportunity name, Stage & target close date

2. **Problem & Impact**
   - 2.1 Core Problem Statement
   - 2.2 Business Impact (risks, value, KPIs)

3. **Current vs Desired State**
   - 3.1 Current State (tools, what's working/not, constraints)
   - 3.2 Desired Future State (outcomes, must-haves, nice-to-haves, non-negotiables)

4. **Buying Dynamics & Risk**
   - 4.1 Stakeholders & Power Map
   - 4.2 Decision Process & Timing
   - 4.3 Perceived Risks

5. **Renessai Fit & Strategy**
   - 5.1 How Renessai Solves Top Pains
   - 5.2 Differentiation vs Status Quo/Competitors
   - 5.3 Delivery & Phasing Idea

6. **Proof & Next Actions**
   - 6.1 Proof Points to Use
   - 6.2 Next Steps (Clear Actions)

### 4.4 Slides Module

(Source: Sections 9, 20.5, 26)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-SLIDES-001 | Template duplication | Duplicate template (never modify original) |
| FR-SLIDES-002 | Layout selection | Select layouts by name using `get_layout_by_name()` |
| FR-SLIDES-003 | Placeholder access | Access placeholders by `idx`, not position |
| FR-SLIDES-004 | Theme colors | Use theme color references (ACCENT_1, etc.) |
| FR-SLIDES-005 | Typography | Keep all text Arial 14pt |
| FR-SLIDES-006 | Content overflow | Split content across slides if overflow (no shrinking) |
| FR-SLIDES-007 | Standard slides | Auto-append standard slides 13-15 from template |
| FR-SLIDES-008 | Link return | Return presentation_id and web_view_link after creation |
| FR-SLIDES-009 | Missing metrics flag | If no KPIs found, mark Slide 8 (BIG_NUMBER) as requiring manual input |
| FR-SLIDES-010 | Version linking | Create "Proposal v2" linked to "Deal Analysis v2" with clear versioning |
| FR-SLIDES-011 | Footer disclaimer | Add footer to all slides: "Draft generated by Proposal Assistant" |

**Slide-to-Layout Mapping:**

| Slide # | Title | Layout | Placeholder Mapping |
|---------|-------|--------|---------------------|
| 1 | Cover Page | TITLE | CENTER_TITLE: "[Client] x Renessai – [Project]", SUBTITLE: "Prepared for..." |
| 2 | Executive Summary | TITLE_AND_BODY | TITLE: "Executive Summary", BODY: situation+stakes+outcomes |
| 3 | Client Context & Objectives | TITLE_AND_TWO_COLUMNS | TITLE: "Client Context & Objectives", BODY(1): current state, BODY(2): desired state |
| 4 | Challenges & Business Impact | TITLE_AND_BODY | TITLE: "Challenges & Business Impact", BODY: problems+risks+impact |
| 5 | Renessai Proposed Solution | SECTION_TITLE_AND_DESCRIPTION | TITLE: "Proposed Solution", SUBTITLE: high-level summary, BODY: key capabilities |
| 6 | Detailed Solution & Scope | TITLE_AND_BODY | TITLE: "Solution Details & Scope", BODY: must-haves, nice-to-haves |
| 7 | Implementation Approach | TITLE_AND_TWO_COLUMNS | TITLE: "Implementation Approach", BODY(1): phases, BODY(2): timeline |
| 8 | Value Case / Expected Outcomes | BIG_NUMBER | TITLE: key metric/outcome, BODY: supporting context |
| 9 | Commercials & Terms | TITLE_AND_BODY | TITLE: "Investment & Terms", BODY: budget, pricing, terms |
| 10 | Risk Mitigation & Assurance | TITLE_AND_TWO_COLUMNS | TITLE: "Risk Mitigation", BODY(1): risks, BODY(2): mitigations |
| 11 | Proof of Success | TITLE_AND_BODY | TITLE: "Proven Results", BODY: case study summaries |
| 12 | Next Steps | TITLE_AND_BODY | TITLE: "Next Steps", BODY: action items with owners and dates |
| 13-15 | Standard Slides | (pre-built) | Auto-appended: Company intro, Team bios, Contact info |

### 4.5 LLM Module

(Source: Sections 12, 20.6)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-LLM-001 | Model configuration | Use Ollama with qwen2.5:14b model |
| FR-LLM-002 | API compatibility | Connect via OpenAI-compatible API |
| FR-LLM-003 | Deal Analysis generation | Generate structured Deal Analysis from inputs |
| FR-LLM-004 | Deck content generation | Generate Proposal Deck content from Deal Analysis |
| FR-LLM-005 | Missing info detection | Identify and return missing information items |
| FR-LLM-006 | Retry with backoff | Implement retry with exponential backoff (1s, 2s, 4s) |
| FR-LLM-007 | Context assembly | Assemble context from transcript, references, and web content |
| FR-LLM-008 | Cloud fallback | If Ollama unavailable, offer cloud LLM (OpenAI/Anthropic) with user consent |
| FR-LLM-009 | Auto-chunking | Split transcripts >32K tokens, summarize chunks, combine results |
| FR-LLM-010 | Updated doc parsing | Re-run LLM on user-uploaded updated Deal Analysis to extract content |

**Token Management:**

| Component | Budget (guideline) |
|-----------|-------------------|
| Transcript | up to 16K–24K tokens |
| References | up to 6K–10K tokens |
| Web content | up to 4K–6K tokens |
| Reserve for output | 4K–8K tokens |
| Target max context | 32K tokens (num_ctx=32768) |

### 4.6 State Module

(Source: Sections 11, 21)

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-STATE-001 | State machine | Implement state machine with 7 states |
| FR-STATE-002 | Thread tracking | Track state per Slack thread (thread_ts) |
| FR-STATE-003 | Approval gate | Enforce approval gate before deck generation |
| FR-STATE-004 | State persistence | Store state before each transition |
| FR-STATE-005 | JSON storage | Support JSON file storage for MVP |
| FR-STATE-006 | State recovery | Support resumption after restart |
| FR-STATE-007 | Template tracking | Track template version at analysis time; detect changes |
| FR-STATE-008 | Version tracking | Track Deal Analysis version (v1, v2, v3) per thread |
| FR-STATE-009 | No timeout | Threads stay in WAITING_FOR_APPROVAL indefinitely (no auto-close) |

**State Machine States:**
- IDLE
- WAITING_FOR_INPUTS
- GENERATING_DEAL_ANALYSIS
- WAITING_FOR_APPROVAL
- GENERATING_DECK
- DONE
- ERROR

**Events:**
- ANALYSE_REQUESTED
- INPUTS_MISSING
- DEAL_ANALYSIS_CREATED
- APPROVED / REJECTED
- UPDATED_DEAL_ANALYSIS_PROVIDED
- DECK_CREATED
- FAILED

**Transition Rules:**
- If transcript missing/empty → WAITING_FOR_INPUTS (do not proceed)
- Always create Deal Analysis before asking for approval
- Only enter GENERATING_DECK after approval ("Yes") OR updated Deal Analysis provided

### 4.7 Web Fetch Module

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-WEB-001 | URL fetching | Fetch content from user-provided URLs for research context |
| FR-WEB-002 | Failure reporting | List failed URLs in Slack message; proceed with available content |
| FR-WEB-003 | Retry logic | Retry failed fetches 2-3 times before reporting failure |

### 4.8 Analytics Module

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-ANALYTICS-001 | Usage dashboard | Full analytics dashboard with charts, trends, user activity |
| FR-ANALYTICS-002 | Request tracking | Track all analysis/deck requests with timestamps |
| FR-ANALYTICS-003 | Error tracking | Track error types, frequencies, and resolution rates |
| FR-ANALYTICS-004 | Quality metrics | Track draft quality scores from user feedback |

**Note:** Analytics dashboard is P3 priority (post-MVP). Basic logging sufficient for MVP.

---

## 5. Non-Functional Requirements

### 5.1 Performance

(Source: Section 19.1)

| ID | Requirement | Target | Notes |
|----|-------------|--------|-------|
| NFR-PERF-001 | Slack acknowledgment | < 3 seconds | Bot should react/reply quickly |
| NFR-PERF-002 | Deal Analysis generation | < 60 seconds | End-to-end from inputs to doc created |
| NFR-PERF-003 | Proposal Deck generation | < 120 seconds | Includes template duplication and population |
| NFR-PERF-004 | LLM response time | < 45 seconds | For qwen2.5:14b with 32K context |
| NFR-PERF-005 | Concurrent users | 5 simultaneous | Based on team size; scale as needed |

### 5.2 Security

(Source: Section 19.2)

| ID | Requirement | Implementation |
|----|-------------|----------------|
| NFR-SEC-001 | No secrets in code | All credentials via environment variables |
| NFR-SEC-002 | No PII in logs | Log only IDs, links, and status codes |
| NFR-SEC-003 | Service account isolation | Dedicated service account for this bot only |
| NFR-SEC-004 | Drive access scoping | Service account has access only to /Clients/ folder tree |
| NFR-SEC-005 | Slack token security | Bot token stored securely, never logged or exposed |
| NFR-SEC-006 | Credential rotation | Service account keys rotated quarterly |
| NFR-SEC-007 | Input sanitization | Validate all user inputs before processing |

### 5.3 Reliability

(Source: Section 19.3)

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-REL-001 | Uptime | 99.5% during business hours (Mon-Fri, 8AM-8PM EET) |
| NFR-REL-002 | Data persistence | State saved before each transition (zero data loss) |
| NFR-REL-003 | Graceful degradation | If LLM fails, user gets clear error + retry option |
| NFR-REL-004 | Recovery time | < 5 minutes for manual restart if needed |
| NFR-REL-005 | State recovery | Bot can resume from last known state after restart |

### 5.4 Maintainability

(Source: Section 19.4)

| ID | Requirement | Implementation |
|----|-------------|----------------|
| NFR-MAIN-001 | Code coverage | > 80% for core modules (state, LLM, Drive) |
| NFR-MAIN-002 | Documentation | README, inline comments, API docstrings |
| NFR-MAIN-003 | Prompt versioning | Prompts stored as separate files with version comments |
| NFR-MAIN-004 | Dependency pinning | All dependencies pinned in pyproject.toml |

---

## 6. API Contracts

### 6.1 Slack → Bot (Inbound Events)

(Source: Section 20.1)

```python
# Message event with attachments
{
    "type": "message",
    "channel": "C1234567890",
    "user": "U1234567890",
    "text": "Analyse",
    "ts": "1706440000.000001",
    "thread_ts": "1706440000.000001",
    "files": [
        {
            "id": "F1234567890",
            "name": "acme-corp-discovery.md",
            "mimetype": "text/markdown",
            "url_private_download": "https://files.slack.com/..."
        }
    ]
}
```

### 6.2 Bot → Slack (Outbound Messages)

(Source: Section 20.2)

```python
# Analysis complete message
{
    "channel": "C1234567890",
    "thread_ts": "1706440000.000001",
    "text": "Deal Analysis created...",
    "blocks": [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Deal Analysis created*"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "<https://docs.google.com/...|View Deal Analysis>"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Missing information:*\n• Budget range\n• Decision timeline"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Should I continue and create a draft proposal deck?"}
        }
    ]
}
```

### 6.3 Drive Client Interface

(Source: Section 20.3)

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

### 6.4 Docs Client Interface

(Source: Section 20.4)

```python
class DocsClient:
    def create_document(self, title: str, folder_id: str) -> tuple[str, str]:
        """
        Create new Google Doc in folder.
        Returns: (doc_id, web_view_link)
        """

    def populate_deal_analysis(self, doc_id: str, content: dict) -> None:
        """
        Populate Deal Analysis template with structured content.
        content: {
            "opportunity_snapshot": {...},
            "problem_impact": {...},
            "current_desired_state": {...},
            "buying_dynamics": {...},
            "renessai_fit": {...},
            "proof_next_actions": {...}
        }
        """
```

### 6.5 Slides Client Interface

(Source: Sections 20.5, 26.5)

```python
class SlidesClient:
    def duplicate_template(self, template_id: str, new_title: str, folder_id: str) -> tuple[str, str]:
        """
        Duplicate template slide deck.
        Returns: (presentation_id, web_view_link)
        """

    def populate_proposal_deck(self, presentation_id: str, content: dict) -> None:
        """
        Populate slides with content mapped from Deal Analysis.
        content: {
            "slide_1_cover": {...},
            "slide_2_executive_summary": {...},
            ...
        }
        """

    def get_layout_for_slide(self, slide_number: int) -> str:
        """Returns layout name for given proposal slide number."""
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
        return SLIDE_LAYOUTS.get(slide_number, "TITLE_AND_BODY")
```

### 6.6 LLM Client Interface

(Source: Section 20.6)

```python
class LLMClient:
    def generate_deal_analysis(
        self,
        transcript: str,
        references: list[str],
        web_content: list[str]
    ) -> dict:
        """
        Generate Deal Analysis from inputs.
        Returns: {
            "content": dict,  # Structured Deal Analysis content
            "missing_info": list[str],  # List of missing items
            "raw_response": str  # For debugging
        }
        Raises: LLMError on failure
        """

    def generate_proposal_deck_content(
        self,
        deal_analysis: dict
    ) -> dict:
        """
        Generate slide content from Deal Analysis.
        Returns: {
            "slides": list[dict],  # Content for each slide
            "raw_response": str
        }
        Raises: LLMError on failure
        """
```

---

## 7. Data Models

### 7.1 Thread State Storage

(Source: Section 21.1)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| thread_ts | string | Yes | Slack thread timestamp (primary key) |
| channel_id | string | Yes | Slack channel ID |
| user_id | string | Yes | Slack user who initiated |
| user_email | string | No | User email (for Drive sharing) |
| client_name | string | No | Extracted client name |
| client_folder_id | string | No | Google Drive client folder ID |
| analyse_folder_id | string | No | "Analyse here" folder ID |
| proposals_folder_id | string | No | "Proposals" folder ID |
| deal_analysis_doc_id | string | No | Created Deal Analysis doc ID |
| deal_analysis_link | string | No | Web link to Deal Analysis |
| slides_deck_id | string | No | Created Proposal Deck ID |
| slides_deck_link | string | No | Web link to Proposal Deck |
| state | enum | Yes | Current state machine state |
| previous_state | enum | No | State before current (for debugging) |
| input_transcript_file_id | string | No | Slack file ID of transcript |
| input_reference_file_ids | json | No | Array of reference file IDs |
| input_urls | json | No | Array of provided URLs |
| missing_info_items | json | No | Array of flagged missing items |
| error_message | string | No | Last error message (if ERROR state) |
| error_type | string | No | Error type code |
| retry_count | integer | No | Number of retries attempted |
| created_at | timestamp | Yes | When thread was first tracked |
| updated_at | timestamp | Yes | Last state change timestamp |

**State Enum Values:** IDLE, WAITING_FOR_INPUTS, GENERATING_DEAL_ANALYSIS, WAITING_FOR_APPROVAL, GENERATING_DECK, DONE, ERROR

### 7.2 Document Metadata

(Source: Section 21.2)

| Field | Type | Description |
|-------|------|-------------|
| doc_id | string | Google Doc/Slides ID |
| doc_type | enum | "deal_analysis" or "proposal_deck" |
| thread_ts | string | Originating Slack thread |
| client_name | string | Client name |
| created_by_user_id | string | Slack user who requested |
| created_at | timestamp | Creation timestamp |
| web_link | string | Shareable link |
| word_count | integer | Approximate word count (for Deal Analysis) |
| slide_count | integer | Number of slides (for Proposal Deck) |

### 7.3 Storage Implementation

(Source: Section 21.3)

For MVP, use simple JSON file storage:

```
data/
├── threads/
│   └── {channel_id}_{thread_ts}.json
└── documents/
    └── {doc_id}.json
```

[TBD - needs product decision]: Consider upgrading to SQLite or Redis for production if concurrent access becomes an issue.

---

## 8. Error Handling Matrix

(Source: Section 15)

| Trigger | Error Code | User Message | System Action | Recovery |
|---------|------------|--------------|---------------|----------|
| No transcript attached | INPUT_MISSING | "Please attach a meeting transcript (.md file) to start." | Stay in IDLE | User retries with attachment |
| Transcript empty/unreadable | INPUT_INVALID | "The transcript file appears to be empty or invalid." | Stay in IDLE | User retries with valid file |
| Drive folder not accessible | DRIVE_PERMISSION | "Unable to access the client folder. Please ensure the bot has access to Drive." | Set ERROR state, log details | Admin check permissions |
| Drive API quota exceeded | DRIVE_QUOTA | "Google Drive is temporarily unavailable. Please try again in a few minutes." | Set ERROR state, retry with backoff | Automatic retry (3x) |
| Google Docs creation fails | DOCS_ERROR | "Failed to create the Deal Analysis document. Please try again." | Set ERROR state, log details | Automatic retry (3x) |
| Google Slides creation fails | SLIDES_ERROR | "Failed to create the proposal deck. Please try again." | Set ERROR state, log details | Automatic retry (3x) |
| LLM API error | LLM_ERROR | "AI service temporarily unavailable. Please try again in a moment." | Set ERROR state, retry with backoff | Automatic retry (3x, 1s/2s/4s) |
| LLM response invalid/empty | LLM_INVALID | "Unable to generate analysis. Please try again or contact support." | Set ERROR state, log response | User retries or escalates |
| Unknown approval response | APPROVAL_UNCLEAR | "Please reply 'Yes' to create the deck, or 'No' to stop." | Stay in WAITING_FOR_APPROVAL | Wait for clear response |
| State not found for thread | STATE_MISSING | "I've lost track of this conversation. Please start over with 'Analyse'." | Reset to IDLE | User restarts flow |
| Non-English transcript | LANGUAGE_UNSUPPORTED | "This transcript appears to be in [detected language]. Currently, only English transcripts are supported." | Stay in IDLE | User provides English transcript |
| Web URL fetch failed | WEB_FETCH_FAILED | "Could not fetch content from: [URL list]. Proceeding with available content." | Continue processing | Informational; no action needed |
| Local LLM unavailable | LLM_OFFLINE | "Local AI service is unavailable. Would you like to use cloud AI? (Your data will be sent securely to OpenAI/Anthropic)" | Show consent buttons | User approves or waits |
| Template version changed | TEMPLATE_CHANGED | "The proposal template has been updated since your Deal Analysis. Continue with new template?" | Show confirmation buttons | User confirms or cancels |
| Transcript too long | TRANSCRIPT_OVERFLOW | "Transcript exceeds token limit. Splitting and summarizing automatically..." | Auto-chunk and continue | Informational; auto-handled |

**Retry Strategy:**
- LLM errors: 3 retries with exponential backoff (1s, 2s, 4s)
- Drive API errors: 3 retries with exponential backoff
- After max retries: notify user, set ERROR state, alert via logging

---

## 9. Security & Compliance Requirements

### 9.1 Data Handling Rules

(Source: Section 16)

- Do NOT log secrets or full transcripts
- Do NOT invent facts—write "Unknown / Not provided" if missing
- Do NOT edit the original Slides template—always duplicate
- Do NOT change theme/fonts/colors/branding
- Do NOT write outside approved client folders
- Do NOT delete/overwrite client docs or decks
- Do NOT expose raw API errors to users—always use friendly messages

### 9.2 Access Control

- Service account owns all created files
- Share with user email as Editor after creation
- Service account scoped to /Clients/ folder only
- Slack bot token stored securely, never logged

### 9.3 Audit Requirements

- Log IDs, links, and status codes only
- No PII in logs
- Retention: [TBD - needs product decision] (default assumption: 90 days)

---

## 10. Dependencies & External Services

### 10.1 External Services

(Source: Section 25.1)

| Service | Purpose | Failure Impact |
|---------|---------|----------------|
| Slack API | Receive messages, send responses | Bot non-functional |
| Google Drive API | Store/retrieve files | Cannot access inputs or save outputs |
| Google Docs API | Create Deal Analysis | Cannot generate Deal Analysis |
| Google Slides API | Create Proposal Deck | Cannot generate Proposal Deck |
| Ollama (local) | LLM inference | Cannot generate content |

### 10.2 Python Dependencies

(Source: Section 25.2)

```toml
[project]
dependencies = [
    "slack-bolt>=1.18.0",
    "google-api-python-client>=2.100.0",
    "google-auth>=2.23.0",
    "openai>=1.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "black>=23.9.0",
    "pyright>=1.1.0",
]
```

### 10.3 Infrastructure Requirements

(Source: Section 25.3)

| Component | Requirement |
|-----------|-------------|
| Python | 3.12+ |
| Ollama | Latest stable, with qwen2.5:14b model pulled |
| RAM | 16GB minimum (32GB recommended for 14B model) |
| GPU | Optional but recommended (NVIDIA with CUDA for faster inference) |
| Network | Outbound HTTPS to Slack and Google APIs |

---

## 11. Testing Strategy

### 11.1 Unit Tests

(Source: Section 22.1)

| Module | Test Focus | Example Test Cases |
|--------|------------|-------------------|
| state/machine.py | State transitions | Valid: IDLE → GENERATING_DEAL_ANALYSIS; Invalid: IDLE → GENERATING_DECK |
| state/storage.py | CRUD operations | Create, read, update thread state; Handle missing thread |
| llm/context_builder.py | Context assembly | Transcript truncation; Reference summarization; Token counting |
| utils/parsing.py | Transcript parsing | Extract client name; Handle empty file; Handle malformed markdown |
| utils/validation.py | Input validation | Valid .md file; Empty file detection; Size limits |
| slack/messages.py | Message formatting | Missing info list; Document links; Error messages |
| drive/folders.py | Folder logic | Path resolution; Name sanitization |
| slides/proposal_deck.py | Layout selection | Correct layout for each slide number; Placeholder idx access |

**Coverage Target:** > 80% for core modules

### 11.2 Integration Tests

(Source: Section 22.2)

| Test Scenario | Components Involved | Verification |
|---------------|---------------------|--------------|
| Slack event → State update | Slack handlers, State machine | State correctly transitions |
| State → Drive folder creation | State machine, Drive client | Folder exists with correct structure |
| LLM call with mock response | LLM client, Context builder | Response parsed correctly |
| Full Deal Analysis flow | All except LLM (mocked) | Doc created, link returned, state = WAITING_FOR_APPROVAL |
| Full Deck flow | All except LLM (mocked) | Deck created from template, state = DONE |
| Slides layout selection | Slides client | Correct layout selected for each slide number |
| Slides placeholder population | Slides client | Placeholders accessed by idx, content populated correctly |

### 11.3 End-to-End Tests

(Source: Section 22.3)

| Scenario | Steps | Expected Outcome |
|----------|-------|-----------------|
| Happy path - full flow | Attach transcript → "Analyse" → "Yes" | Deal Analysis + Proposal Deck created |
| Rejection path | Attach transcript → "Analyse" → "No" | Only Deal Analysis created, bot stops |
| Updated Deal Analysis | Attach transcript → "Analyse" → attach updated doc → "Use this" | Deck uses updated content |
| Missing transcript | "Analyse" (no attachment) | Error message, stays IDLE |
| Empty transcript | Attach empty .md → "Analyse" | Error message, stays IDLE |
| LLM timeout + retry | Simulate LLM timeout | Retries 3x, then ERROR state |
| Recovery after error | ERROR state → user retries | Successful completion |
| Multiple reference files | Attach transcript + 3 references | All references included in context |

### 11.4 Test Environment

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/proposal_assistant --cov-report=html

# Run specific test module
uv run pytest tests/unit/test_state_machine.py

# Run integration tests only
uv run pytest tests/integration/ -v
```

### 11.5 Test Fixtures

```
tests/
├── fixtures/
│   ├── transcripts/
│   │   ├── valid_transcript.md
│   │   ├── empty_transcript.md
│   │   └── long_transcript.md
│   ├── llm_responses/
│   │   ├── deal_analysis_response.json
│   │   └── proposal_deck_response.json
│   └── slack_events/
│       ├── message_with_file.json
│       └── approval_yes.json
├── unit/
├── integration/
└── e2e/
```

---

## 12. Rollout Plan

### Phase 1: Internal Alpha (Week 1-2)

(Source: Section 23)

| Activity | Details |
|----------|---------|
| Deployment | Deploy to dedicated test Slack channel: `#proposal-assistant-alpha` |
| Users | 2-3 internal developers + 1 sales team member |
| Monitoring | Manual review of ALL interactions |
| Data | Use test client folders only (not real client data) |
| Goal | Validate core flow works end-to-end |
| Exit Criteria | 10 successful full flows with no critical bugs |

### Phase 2: Limited Beta (Week 3-4)

| Activity | Details |
|----------|---------|
| Deployment | Enable in main Slack workspace, invite-only |
| Users | 5-10 consultants/salespeople (early adopters) |
| Monitoring | Daily review of error logs; Weekly feedback sync |
| Data | Real client data with extra oversight |
| Goal | Validate quality of outputs; Gather UX feedback |
| Feedback | Slack survey after each use (thumbs up/down + optional comment) |
| Exit Criteria | > 80% positive feedback; < 5% error rate |

### Phase 3: General Availability (Week 5-6)

| Activity | Details |
|----------|---------|
| Deployment | Announce in `#general`; Add to company tooling docs |
| Users | All Renessai consultants and salespeople |
| Monitoring | Automated alerting on error rate spike |
| Documentation | User guide; FAQ; Troubleshooting guide |
| Support | Designated point of contact for issues |
| Goal | Full adoption for new proposal workflows |

### Phase 4: Optimization (Ongoing)

| Activity | Details |
|----------|---------|
| Performance | Monitor and optimize LLM response times |
| Quality | Periodic review of Deal Analysis accuracy |
| Features | Collect feature requests; Prioritize roadmap |
| Scaling | Evaluate need for dedicated LLM infrastructure |

### Rollback Plan

If critical issues arise:

1. Disable bot responses (set `BOT_ENABLED=false`)
2. Post message in Slack: "Proposal Assistant is temporarily offline for maintenance"
3. Investigate and fix
4. Re-enable with announcement

---

## Appendix A: Proposal Template Specification

(Source: Section 26)

### A.1 Template Metadata

| Property | Value |
|----------|-------|
| Template name | Renessai basic template 10_2025.pptx |
| Slide dimensions | 10.0" × 5.62" (16:9 widescreen) |
| Total slide masters | 2 |
| Template location | `Drive / Templates / Renessai Proposal Template` |
| Environment variable | `PROPOSAL_TEMPLATE_SLIDE_ID` |

### A.2 Brand Color Theme (Renessai)

Use **Theme 3 - Simple Light Green** as the primary brand theme:

| Color Role | Hex Code | Usage |
|------------|----------|-------|
| dark1 | #081F09 | Primary text |
| light1 | #FFFFFF | Primary background |
| dark2 | #244231 | Secondary text / headers |
| light2 | #D6D1CA | Secondary background / subtle fills |
| accent1 | #EAFF01 | Primary accent (Renessai yellow-green) |
| accent2 | #0D1F08 | Dark accent |
| accent3 | #BBF92B | Highlight / call-to-action |
| accent4 | #7EBC00 | Success / positive indicators |
| accent5 | #346D55 | Muted green accent |
| accent6 | #264634 | Dark green accent |
| hyperlink | #7EBC00 | Link color |

**Rule:** Do NOT override these colors programmatically. Use theme color references (e.g., `scheme_color='ACCENT_1'`), not hardcoded hex values.

### A.3 Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Titles | Arial | 14pt | Regular |
| Body text (all levels) | Arial | 14pt | Regular |
| Headings | Arial | 14pt | Regular |

**Rule:** Do NOT change fonts or sizes. Content must fit within placeholder bounds; if too long, split across slides rather than shrinking text.

### A.4 Available Slide Layouts

| Layout Name | Placeholders | Best Used For |
|-------------|--------------|---------------|
| TITLE | CENTER_TITLE (idx=0), SUBTITLE (idx=1), SLIDE_NUMBER (idx=12) | Cover page (Slide 1) |
| SECTION_HEADER | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Section dividers |
| TITLE_AND_BODY | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Standard content slides |
| TITLE_AND_TWO_COLUMNS | TITLE (idx=0), BODY (idx=1), BODY (idx=2), SLIDE_NUMBER (idx=12) | Comparison / side-by-side |
| TITLE_ONLY | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Custom content slides |
| ONE_COLUMN_TEXT | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Narrow text with image space |
| MAIN_POINT | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Key takeaway / quote slides |
| SECTION_TITLE_AND_DESCRIPTION | TITLE (idx=0), SUBTITLE (idx=1), BODY (idx=2), SLIDE_NUMBER (idx=12) | Section intro with context |
| CAPTION_ONLY | BODY (idx=1), SLIDE_NUMBER (idx=12) | Image-heavy slides |
| BIG_NUMBER | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Metrics / KPI highlights |
| BLANK | SLIDE_NUMBER (idx=12) | Fully custom slides |

### A.5 Placeholder Position Reference (inches)

```json
{
  "TITLE": {
    "CENTER_TITLE": {"left": 0.34, "top": 0.81, "width": 9.32, "height": 2.24},
    "SUBTITLE": {"left": 0.34, "top": 3.1, "width": 9.32, "height": 0.87}
  },
  "TITLE_AND_BODY": {
    "TITLE": {"left": 0.34, "top": 0.49, "width": 9.32, "height": 0.63},
    "BODY": {"left": 0.34, "top": 1.26, "width": 9.32, "height": 3.74}
  },
  "TITLE_AND_TWO_COLUMNS": {
    "TITLE": {"left": 0.34, "top": 0.49, "width": 9.32, "height": 0.63},
    "BODY_LEFT": {"left": 0.34, "top": 1.26, "width": 4.37, "height": 3.74},
    "BODY_RIGHT": {"left": 5.28, "top": 1.26, "width": 4.37, "height": 3.74}
  },
  "BIG_NUMBER": {
    "TITLE": {"left": 0.34, "top": 1.21, "width": 9.32, "height": 2.15},
    "BODY": {"left": 0.34, "top": 3.45, "width": 9.32, "height": 1.42}
  },
  "SECTION_TITLE_AND_DESCRIPTION": {
    "TITLE": {"left": 0.29, "top": 1.35, "width": 4.42, "height": 1.62},
    "SUBTITLE": {"left": 0.29, "top": 3.07, "width": 4.42, "height": 1.35},
    "BODY": {"left": 5.4, "top": 0.79, "width": 4.2, "height": 4.04}
  }
}
```

### A.6 Full Template JSON Reference

The complete template specification is stored at: `config/proposal_template_spec.json`

This file contains:
- Presentation settings (dimensions, aspect ratio)
- Complete color scheme with all theme colors
- Typography settings
- All slide layouts with placeholder positions and indices
- Layout-to-slide mapping for proposal generation

---

## Known TBDs

(Source: Section 24, updated with stakeholder decisions)

### Resolved Items

| Item | Decision | Notes |
|------|----------|-------|
| Multi-language support | English only, reject others | Show clear error if non-English detected |
| Concurrent request handling | Sequential processing | One request at a time with queue |
| Feedback mechanism | Slack reactions + survey | Thumbs up/down after generation |
| Template versioning | Notify and re-confirm | If template changed, ask user before proceeding |
| LLM fallback strategy | Cloud with user consent | Ask permission before using cloud API |
| Approval UX | Button-based UI | Slack interactive buttons instead of text |
| Document sharing | Channel members | All channel members get Editor access |
| Long transcript handling | Auto-chunk and summarize | Split >32K tokens, summarize, combine |
| Regeneration support | Versioned (v2, v3) | Create new docs, keep previous versions |
| Approval timeout | No timeout | Wait forever; threads never auto-close |

### Still TBD

| Item | Context | Default Assumption |
|------|---------|-------------------|
| Default num_ctx for Ollama | Token management | 32768 for dev; TBD for prod based on hardware |
| State storage backend | JSON vs SQLite vs Redis | JSON files for MVP |
| Support SLA | Response time for user issues | Best-effort during beta |
| Audit log retention | How long to keep logs | 90 days |
| Analytics dashboard scope | Charts, metrics, exports | Full dashboard (P3 priority) |
| Case study taxonomy | Industry categories | Use folder names for keyword matching |

---

*End of Product Requirements Document*
