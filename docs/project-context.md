# LLM Coding Task (Ollama + Qwen2.5)

Generate a complete Product Requirements Document ([prd.md](http://prd.md)) for the Proposal Assistant Slack Bot. The PRD must include:

- Executive Summary
- Goals & Success Metrics
- User Stories with acceptance criteria
- Functional Requirements (organized by module)
- Non-Functional Requirements (performance, security, reliability)
- API Contracts between components (Slack ↔ Bot ↔ Drive ↔ Docs ↔ Slides)
- Data Models (state storage schema, document metadata)
- Error Handling Matrix (trigger → error → user message → recovery)
- Security & Compliance Requirements
- Dependencies & External Services
- Testing Strategy (unit, integration, e2e)
- Rollout Plan

Use ONLY the information in this context file. If something is unspecified, flag it as "\[TBD - needs product decision\]" rather than inventing details.

---

## Tech Stack (Implementation)

| Component | Technology |
| --- | --- |
| Language/runtime | Python 3.12 |
| Workflow/tooling | uv |
| Slack | Bolt for Python (slack_bolt) |
| Google APIs | google-api-python-client, google-auth (service account) |
| LLM | Ollama (local) + openai Python SDK (OpenAI-compatible endpoint) |
| Config/env | OS env vars in production; .env in local dev (optional: python-dotenv) |
| Testing | pytest |
| Lint/format | ruff (lint) + black (format) |
| Typing (recommended) | pyright or mypy |

---

## Repo Conventions

- Prefer a `src/` layout (`src/proposal_assistant/...`) OR a simple `app/` package. Either is fine—be consistent.
- All secrets come from env vars (never hardcode tokens/keys).

---

## Expected Module Structure

```
src/proposal_assistant/
├── __init__.py
├── main.py                # Entry point, initializes Bolt app
├── config.py              # Environment variables, constants
│
├── slack/
│   ├── __init__.py
│   ├── handlers.py        # Message/event handlers
│   ├── commands.py        # Slash commands (if any)
│   └── messages.py        # Message templates/formatters
│
├── drive/
│   ├── __init__.py
│   ├── client.py          # Google Drive API wrapper
│   ├── folders.py         # Folder navigation/creation
│   └── permissions.py     # Sharing/access management
│
├── docs/
│   ├── __init__.py
│   ├── client.py          # Google Docs API wrapper
│   └── deal_analysis.py   # Deal Analysis generation logic
│
├── slides/
│   ├── __init__.py
│   ├── client.py          # Google Slides API wrapper
│   └── proposal_deck.py   # Proposal Deck generation logic
│
├── llm/
│   ├── __init__.py
│   ├── client.py          # LLM API client (Ollama / OpenAI-compatible)
│   ├── prompts/
│   │   ├── deal_analysis.py   # Prompts for Deal Analysis
│   │   └── proposal_deck.py   # Prompts for Proposal Deck
│   └── context_builder.py # Assembles context from inputs
│
├── state/
│   ├── __init__.py
│   ├── machine.py         # State machine implementation
│   └── storage.py         # Thread state persistence
│
└── utils/
    ├── __init__.py
    ├── parsing.py         # Transcript/markdown parsing
    └── validation.py      # Input validation
```

---

# Project Context — Proposal Assistant (Slack Bot)

**Purpose of this file:** give an LLM coding assistant enough context to work inside this repo without guessing. Keep changes aligned with the product goals and the real workflow.

---

## 1) What This Project Is

**Proposal Assistant** is a Slack bot used by consultants and salespeople at **Renessai**. It turns real client discovery inputs into two draft outputs:

1. A structured **Deal Analysis** (Google Doc)
2. A first-draft **Proposal Deck** (Google Slides) following Renessai's standard structure

The main goal is to create draft proposal decks faster, reduce manual copy-paste, and keep outputs grounded in real sources (meeting notes + existing references + web links).

**Last updated:** 2026-01-28

---

## 2) Who Uses It

- **Primary users:** Renessai consultants and salespeople
- **Bot name in Slack:** "Proposal Assistant"
- Human approval is required before creating a proposal deck.

---

## 3) Big Rules (Must Follow)

### 3.1 Grounded Content (No Guessing)

- Prefer meeting transcript language (client words) wherever possible.
- Use only provided inputs (transcripts, Drive references, provided web links).
- If key info is missing, say what is missing instead of inventing details.

### 3.2 Simple, Usable Drafts

- Outputs are drafts meant to be reviewed and edited by humans.
- Keep language clear. Avoid filler. Keep structure consistent.

### 3.3 Two-Step Workflow

- **Step A:** Generate Deal Analysis Doc (always)
- **Step B:** Generate Proposal Deck (only after a human says "Yes" or provides an updated Deal Analysis)

---

## 4) Inputs (What Users Provide)

Users provide inputs to the Slack bot:

### 1. Meeting Transcription File

- **Source:** Fireflies (or similar)
- **File type:** .md
- **Typical Drive path:** `Drive / Clients / ClientName / Meetings /`

### 2. Extra Reference Data in Drive (optional but recommended)

- Old proposals for the same client
- Old project decks
- Similar proposals for other clients
- Company proposal templates and rules

### 3. Web Research Link(s) (URL)

- Outside facts about the client (still must be relevant and used carefully)

---

## 5) Outputs (What the Bot Creates)

### 5.1 Deal Analysis (Google Doc)

- **File name:** "Deal Analysis"
- **Saved to:** `Drive / Clients / ClientName / Analyse here /`
- The doc uses the exact template in section 8 below.

### 5.2 Draft Proposal Deck (Google Slides)

- New draft deck created after approval
- **Saved to:** `Drive / Clients / ClientName / Proposals /`
- Uses the deck outline in section 9 below

### 5.3 Slack Notifications

- **After Deal Analysis:** send a message with the Drive link, plus missing info list (if any), and ask whether to continue.
- **After Deck Creation:** send a message with the deck link.

---

## 6) End-to-End Workflow (Slack)

### Step 1 — User Starts Analysis

User attaches:

- transcript .md
- optional Drive reference files
- optional URL(s)

Then asks the bot: **"Analyse"**

### Step 2 — Bot Creates Deal Analysis

Bot acts like a senior salesperson / AI consulting advisor:

- Thinks in two layers:
  1. Who the client is + how they buy
  2. What business problem is being solved (and impact)

Bot outputs:

- Deal Analysis doc link
- Missing information list (A, B, C…) if needed
- A question: *"Should I continue and create a draft proposal deck?"*

### Step 3 — Human Decision

- Reply **"Yes"** → bot continues to deck creation
- Reply **"No"** → bot stops
- Or user attaches an updated Deal Analysis → bot uses the updated version to generate the deck

### Step 4 — Bot Creates Proposal Deck

Bot generates slides following Renessai structure and saves to Drive.

### Step 5 — Done Signal

Bot sends: "Draft proposal deck created" + Drive link.

---

## 7) What "Good" Looks Like (Acceptance Checklist)

- [ ] User can run analysis by attaching inputs and typing "Analyse"

- [ ] Deal Analysis doc is created in the correct Drive location with the correct template

- [ ] Bot highlights missing information instead of guessing

- [ ] Deck is created only after explicit approval ("Yes") or an updated Deal Analysis is provided

- [ ] Deck follows Renessai slide structure and maps content from the Deal Analysis

- [ ] Slack messages always include links to created documents

---

## 8) Deal Analysis — Required Google Doc Template

Keep headings and numbering the same so downstream deck generation is consistent.

### 1. Opportunity Snapshot

Client / Opportunity basics.

| Field | Value |
| --- | --- |
| Company |  |
| Industry / Segment |  |
| Size (revenue / employees / region) |  |
| Contact(s) + roles |  |
| Opportunity name / CRM link |  |
| Stage & target close date |  |

### 2. Problem & Impact (In The Client's Words)

#### 2.1 Core Problem Statement

How does the client describe their main pain or opportunity?

**One-sentence problem (client language):**

#### 2.2 Business Impact

- **What happens if they do nothing?** (risks, lost revenue, inefficiency):
- **What value exists if we solve it?** (savings, growth, risk reduction):
- **Key metrics they care about** (KPIs / targets):

### 3. Current vs Desired State

#### 3.1 Current State

- **Existing tools / vendors / processes:**
- **What's working:**
- **What's not working:**
- **Key constraints** (budget, data, integrations, people, compliance):

#### 3.2 Desired Future State (3-6-12 months)

- **How success looks** (2–3 measurable outcomes):
- **Must-haves:**
- **Nice-to-haves:**
- **Non-negotiables** (security, compliance, support, etc.):

### 4. Buying Dynamics & Risk

#### 4.1 Stakeholders & Power Map

- **Economic buyer** (budget owner):
- **Primary sponsor / champion:**
- **Key users / departments:**
- **Influencers / blockers** (IT, finance, legal, etc.):

#### 4.2 Decision Process & Timing

- **Decision steps** (who, in what order):
- **Key dates** (RFP, demo, pilot, go-live):
- **Procurement requirements** (approved vendor, contract terms, etc.):
- **Budget situation** (range / confirmed / exploratory):

#### 4.3 Perceived Risks

- **What are they most afraid of?** (implementation, adoption, data, vendor risk):
- **Past bad experiences mentioned:**

### 5. Renessai Fit & Strategy

#### 5.1 How Renessai Solves Their Top Pains

**Top 3 client pains:**\
1.\
2.\
3.

**Matching Renessai capabilities / offerings:**

- For (1):
- For (2):
- For (3):

#### 5.2 Differentiation vs Status Quo / Competitors

- **Why change at all** (vs doing nothing):
- **Why Renessai** (vs other options):

#### 5.3 Delivery & Phasing Idea

- **Recommended approach** (pilot / phased rollout / full rollout):
- **Rough timeline & phases:**
- **Client resources needed** (project owner, champions, tech support):

### 6. Proof & Next Actions

#### 6.1 Proof Points to Use

- **Relevant case studies** (industry / use case / size):
- **Results or benchmarks we should highlight:**

#### 6.2 Next Steps (Clear Actions)

- **Internal actions (Renessai):**
- **Client-side actions:**
- **Proposed date for:**
  - Next meeting / workshop:
  - Proposal or concept deck:

---

## 9) Proposal Deck — Required Slide Structure (Google Slides)

The deck is created only after approval. Map content from the Deal Analysis sections shown below.

| Slide | Title | Source from Deal Analysis |
| --- | --- | --- |
| 1 | Cover Page | Opportunity Snapshot (1): "\[Client Name\] x Renessai – \[Project / Initiative Name\]", Date, prepared for, prepared by |
| 2 | Executive Summary | Problem & Impact (2), Desired future state (3.2): Situation in brief, what is at stake, proposed outcomes (2–3 KPIs, timeframe), high-level solution summary |
| 3 | Client Context & Objectives | Opportunity Snapshot (1), Current state (3.1), Desired state (3.2) |
| 4 | Challenges & Business Impact | Problem & Impact (2), Perceived risks (4.3) |
| 5 | Renessai Proposed Solution — Overview | Renessai Fit (5.1, 5.2) |
| 6 | Detailed Solution & Scope | Must-haves / nice-to-haves / non-negotiables (3.2), Matching capabilities (5.1) |
| 7 | Implementation Approach & Timeline | Delivery & phasing idea (5.3), Decision timing (4.2) |
| 8 | Value Case / Expected Outcomes | Business impact + value if solved (2.2), Success outcomes (3.2) |
| 9 | Commercials & Terms | Budget situation (4.2), Phasing idea (5.3) if pricing by phase |
| 10 | Risk Mitigation & Assurance | Perceived risks (4.3), Differentiation (5.2) |
| 11 | Proof of Success (Case Studies & References) | Proof points to use (6.1) |
| 12 | Next Steps | Next steps (6.2) |
| 13+ | Standard Renessai Slides | Auto-appended: Company intro, Team bios, Contact info |

---

## 10) Missing Information Handling (Required Behavior)

When info is missing, the bot should:

1. List missing items clearly in Slack (e.g., "Missing: buyer name, budget range, timeline")
2. Keep producing the draft using only what is known
3. Label uncertain areas as "Unknown / Not provided yet"

**Never invent:**

- Budgets
- Timelines
- Stakeholder names/titles
- Metrics/results
- Client constraints

---

## 11) Implementation Notes (What the Code Should Support)

These are system responsibilities. If repo already has patterns, follow them.

| Component | Responsibility |
| --- | --- |
| Slack | Receive messages + attachments + URLs, and reply in thread |
| Drive | Locate inputs and write outputs into the correct client folders |
| Docs | Create Deal Analysis doc with the template above |
| Slides | Create deck with the structure above |
| Permissions | Ensure the user/team can access created files |
| Logging | Avoid logging sensitive client content; log IDs/links and status instead |

### Explicit State Machine (Approval Gate is Enforced)

This bot is intentionally a two-step process with a hard stop in the middle.

**States:**

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
- APPROVED (user replies "Yes")
- REJECTED (user replies "No")
- UPDATED_DEAL_ANALYSIS_PROVIDED
- DECK_CREATED
- FAILED

**Transition Rules (Guards):**

- If transcript missing/empty → WAITING_FOR_INPUTS (do not proceed)
- Always create Deal Analysis before asking for approval
- Only enter GENERATING_DECK after approval ("Yes") OR updated Deal Analysis provided

**Minimum State Data to Track (store by Slack thread):**

- thread_ts
- client_folder_id
- deal_analysis_doc_id
- slides_deck_id
- last_state

---

## 12) LLM Integration

### Model Configuration

| Setting | Value |
| --- | --- |
| Primary model | qwen2.5:14b (local via Ollama) |
| API | Ollama local server (OpenAI-compatible Chat Completions API) |
| Environment variables | OLLAMA_BASE_URL, OLLAMA_MODEL |

### Local Setup (Developer)

```bash
# Install Ollama (per your OS) and pull the model
ollama pull qwen2.5:14b
```

**Notes:**

- The bot calls Ollama on the same machine via OLLAMA_BASE_URL (default: <http://localhost:11434/v1>).
- If you need larger context windows for long transcripts, raise Ollama's context setting (often called num_ctx) in your local environment.
- \[TBD - decide the default num_ctx for dev/prod\]

### Context Assembly Strategy

The LLM receives a structured prompt with these components (in order):

1. **System prompt:** Role definition (senior sales advisor / AI consulting expert)
2. **Client transcript:** Full meeting transcript (.md content)
3. **Reference documents:** Summaries of attached Drive files (not full content to manage token limits)
4. **Web research:** Extracted content from provided URLs
5. **Output template:** The exact Deal Analysis or Slide structure to follow

### Token Management

Qwen2.5 runs locally via Ollama, so the usable context window depends on your Ollama configuration (num_ctx) and available RAM/VRAM.

**Default Ollama context is often 4K; for this project, set num_ctx to at least 32K in local dev, and tune upward only if your machine can handle it.**

| Component | Budget (guideline) |
| --- | --- |
| Transcript | up to 16K–24K tokens (chunk/summarize if larger) |
| References | up to 6K–10K tokens (summarize if larger) |
| Web content | up to 4K–6K tokens (extract only relevant sections) |
| Reserve for output | 4K–8K tokens |
| Target max context | 32K tokens (num_ctx=32768) |

### Prompt Files

Store prompts as separate files for maintainability:

```
src/proposal_assistant/llm/prompts/
├── system_sales_advisor.txt      # System prompt for Deal Analysis
├── deal_analysis_template.txt    # Output format instructions
├── proposal_deck_template.txt    # Slide mapping instructions
└── missing_info_detector.txt     # Prompt to identify gaps
```

### LLM Call Pattern (Pseudocode)

```python
import os
from openai import OpenAI

# Ollama exposes an OpenAI-compatible endpoint when you use /v1
client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OLLAMA_API_KEY", "ollama")  # not used by Ollama; required by SDK
)

model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

context = build_context(transcript, references, web_content)

response = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": SYSTEM_SALES_ADVISOR},
        {"role": "user", "content": context + DEAL_ANALYSIS_TEMPLATE},
    ],
    temperature=0.2,
    max_tokens=6000,
)

text_out = response.choices[0].message.content
```

---

## 13) Configuration & Environment

### Drive Folder Structure

```
Google Drive/
└── Clients/
    └── {ClientName}/           # Folder named exactly as client company name
        ├── Meetings/           # Input: transcripts stored here
        ├── Analyse here/       # Output: Deal Analysis docs
        ├── Proposals/          # Output: Proposal decks
        └── References/         # Optional: old proposals, project decks
```

### Environment Variables (Required)

```bash
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...          # For Socket Mode
SLACK_SIGNING_SECRET=...

# Google (Service Account)
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}  # Or path to JSON file
GOOGLE_DRIVE_ROOT_FOLDER_ID=1ABC...   # "Clients" folder ID

# LLM (local)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:14b

# Optional (performance tuning)
OLLAMA_NUM_CTX=32768

# Templates
PROPOSAL_TEMPLATE_SLIDE_ID=1XYZ...    # Renessai Proposal Template ID

# App
LOG_LEVEL=INFO
ENVIRONMENT=production   # or "development"
```

### Client Folder Resolution

- Bot extracts client name from transcript filename or user message
- Bot searches for existing folder: `Drive / Clients / {ClientName}`
- If not found: create new folder structure automatically
- Store `client_folder_id` in thread state for subsequent operations

### Slack User → Drive Permissions

- Service account owns all created files
- After creation, bot shares file with the Slack user's email (looked up via `users.info` API)
- Share permission level: "Editor"

### Standard Renessai Slides

- **Template location:** `Drive / Templates / Renessai Proposal Template`
- **Template ID (env var):** PROPOSAL_TEMPLATE_SLIDE_ID
- Bot duplicates this template, then populates slides
- Standard slides appended automatically:
  - Company intro (slide 13)
  - Team bios (slide 14)
  - Contact info (slide 15)

### Case Studies Repository

- **Location:** `Drive / Marketing / Case Studies /`
- Organized by: `{Industry} / {CaseStudyName}.pdf`
- Bot searches by industry keyword match from Deal Analysis section 1

---

## 14) Example Slack Interactions

### Happy Path — Full Flow

```
USER attaches: acme-corp-discovery-call.md
USER: "Analyse"

BOT: "🔍 Analyzing transcript for Acme Corp... 📄 Reading 1 reference file from Drive..."

BOT: "✅ Deal Analysis created:
     📎 https://docs.google.com/document/d/abc123
     
     ⚠️ Missing information:
     • Budget range (not mentioned in call)
     • Decision timeline (unclear)
     • IT stakeholder name
     
     Should I continue and create a draft proposal deck?"

USER: "Yes"

BOT: "📊 Creating proposal deck..."

BOT: "✅ Draft proposal deck created:
     📎 https://docs.google.com/presentation/d/xyz789
     
     The deck is ready for your review and editing."
```

### User Provides Updated Deal Analysis

```
USER attaches: updated-deal-analysis.docx
USER: "Use this updated analysis for the deck"

BOT: "📊 Creating proposal deck from updated Deal Analysis..."

BOT: "✅ Draft proposal deck created:
     📎 https://docs.google.com/presentation/d/xyz789"
```

### User Declines Deck Creation

```
BOT: "Should I continue and create a draft proposal deck?"

USER: "No"

BOT: "👍 Understood. The Deal Analysis is ready for your review.
     Let me know when you'd like to create a proposal deck."
```

### Error — No Transcript

```
USER: "Analyse"

BOT: "❌ I need a meeting transcript to start the analysis.
     Please attach a .md transcript file and try again."
```

### Error — Empty/Invalid Transcript

```
USER attaches: empty-file.md
USER: "Analyse"

BOT: "❌ The transcript file appears to be empty or invalid.
     Please attach a valid meeting transcript (.md) with content."
```

---

## 15) Error Handling Matrix

| Trigger | Error Type | User Message | Bot Action |
| --- | --- | --- | --- |
| No transcript attached | INPUT_MISSING | "Please attach a meeting transcript (.md file) to start." | Stay in IDLE |
| Transcript empty/unreadable | INPUT_INVALID | "The transcript file appears to be empty or invalid." | Stay in IDLE |
| Drive folder not accessible | DRIVE_PERMISSION | "Unable to access the client folder. Please ensure the bot has access to Drive." | Set ERROR state, log details |
| Drive API quota exceeded | DRIVE_QUOTA | "Google Drive is temporarily unavailable. Please try again in a few minutes." | Set ERROR state, implement retry |
| Google Docs creation fails | DOCS_ERROR | "Failed to create the Deal Analysis document. Please try again." | Set ERROR state, log details |
| Google Slides creation fails | SLIDES_ERROR | "Failed to create the proposal deck. Please try again." | Set ERROR state, log details |
| LLM API error | LLM_ERROR | "AI service temporarily unavailable. Please try again in a moment." | Set ERROR state, implement retry with backoff |
| LLM response invalid/empty | LLM_INVALID | "Unable to generate analysis. Please try again or contact support." | Set ERROR state, log response |
| Unknown approval response | APPROVAL_UNCLEAR | "Please reply 'Yes' to create the deck, or 'No' to stop." | Stay in WAITING_FOR_APPROVAL |
| State not found for thread | STATE_MISSING | "I've lost track of this conversation. Please start over with 'Analyse'." | Reset to IDLE |

### Retry Strategy

- **LLM errors:** 3 retries with exponential backoff (1s, 2s, 4s)
- **Drive API errors:** 3 retries with exponential backoff
- **After max retries:** notify user, set ERROR state, alert via logging

---

## 16) Do NOT List (Strict Rules)

- Do NOT create a proposal deck unless the user explicitly approves ("Yes") or provides an updated Deal Analysis.
- Do NOT invent facts. If missing, write "Unknown / Not provided" and list what's needed.
- Do NOT edit the original Slides template—always duplicate it.
- Do NOT change theme/fonts/colors/branding.
- Do NOT log secrets or full transcripts.
- Do NOT refactor unrelated code.
- Do NOT add dependencies unless necessary and explained.
- Do NOT rename/move files unless required.
- Do NOT write outside approved client folders.
- Do NOT delete/overwrite client docs or decks.
- Do NOT proceed on empty/broken transcript.
- Do NOT shrink text to unreadable sizes; split slides instead.
- Do NOT call LLM APIs without proper error handling and retry logic.
- Do NOT expose raw API errors to users; always use friendly messages.

---

## 17) Glossary

| Term | Definition |
| --- | --- |
| Deal Analysis | Structured Google Doc summarizing client discovery findings |
| Proposal Deck | Google Slides presentation following Renessai template |
| Transcript | Meeting notes/transcription file (.md) from Fireflies or similar |
| Approval Gate | Required human confirmation before deck generation |
| Client Folder | Drive folder structure for each client under /Clients/{ClientName}/ |

---

## 18) Success Metrics & KPIs

Quantifiable goals to measure the bot's effectiveness:

| Metric | Target | Measurement Method |
| --- | --- | --- |
| Time to first Deal Analysis draft | &lt; 5 minutes | Timestamp: message received → doc link sent |
| Time to Proposal Deck draft | &lt; 3 minutes | Timestamp: approval received → deck link sent |
| User adoption rate | 80% of new proposals use the bot within 3 months | Count proposals created via bot vs manual |
| Draft quality score | &gt; 4/5 average rating | Post-generation survey (optional Slack reaction) |
| Missing info accuracy | 90%+ of flagged items are genuinely missing | Spot-check audits by sales leads |
| Error rate | &lt; 5% of requests result in ERROR state | Logging and monitoring |
| User retry rate | &lt; 10% of users need to retry due to bot errors | Track FAILED → retry sequences |

---

## 19) Non-Functional Requirements

### 19.1 Performance

| Requirement | Target | Notes |
| --- | --- | --- |
| Slack acknowledgment | &lt; 3 seconds | Bot should react/reply quickly to show it's working |
| Deal Analysis generation | &lt; 60 seconds | End-to-end from inputs received to doc created |
| Proposal Deck generation | &lt; 120 seconds | Includes template duplication and content population |
| LLM response time | &lt; 45 seconds | For qwen2.5:14b with 32K context |
| Concurrent users | 5 simultaneous requests | Based on team size; scale as needed |

### 19.2 Security

| Requirement | Implementation |
| --- | --- |
| No secrets in code | All credentials via environment variables |
| No PII in logs | Log only IDs, links, and status codes |
| Service account isolation | Dedicated service account for this bot only |
| Drive access scoping | Service account has access only to /Clients/ folder tree |
| Slack token security | Bot token stored securely, never logged or exposed |
| Credential rotation | Service account keys rotated quarterly |
| Input sanitization | Validate all user inputs before processing |

### 19.3 Reliability

| Requirement | Target |
| --- | --- |
| Uptime | 99.5% during business hours (Mon-Fri, 8AM-8PM EET) |
| Data persistence | State saved before each transition (zero data loss) |
| Graceful degradation | If LLM fails, user gets clear error + retry option |
| Recovery time | &lt; 5 minutes for manual restart if needed |
| State recovery | Bot can resume from last known state after restart |

### 19.4 Maintainability

| Requirement | Implementation |
| --- | --- |
| Code coverage | &gt; 80% for core modules (state, LLM, Drive) |
| Documentation | README, inline comments, API docstrings |
| Prompt versioning | Prompts stored as separate files with version comments |
| Dependency pinning | All dependencies pinned in pyproject.toml |

---

## 20) API Contracts Between Components

### 20.1 Slack → Bot (Inbound Events)

```python
# Message event with attachments
{
    "type": "message",
    "channel": "C1234567890",
    "user": "U1234567890",
    "text": "Analyse",
    "ts": "1706440000.000001",
    "thread_ts": "1706440000.000001",  # Same as ts if new thread
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

### 20.2 Bot → Slack (Outbound Messages)

```python
# Analysis complete message
{
    "channel": "C1234567890",
    "thread_ts": "1706440000.000001",
    "text": "✅ Deal Analysis created...",
    "blocks": [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "✅ *Deal Analysis created*"}
        },
        {
            "type": "section", 
            "text": {"type": "mrkdwn", "text": "📎 <https://docs.google.com/...|View Deal Analysis>"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "⚠️ *Missing information:*\\n• Budget range\\n• Decision timeline"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "Should I continue and create a draft proposal deck?"}
        }
    ]
}
```

### 20.3 Bot → Drive API

```python
# Interface: DriveClient
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

### 20.4 Bot → Docs API

```python
# Interface: DocsClient
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

### 20.5 Bot → Slides API

```python
# Interface: SlidesClient
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
```

### 20.6 Bot → LLM (Ollama)

```python
# Interface: LLMClient
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

## 21) Data Models (Full Schema)

### 21.1 Thread State Storage

Primary storage for tracking conversation state per Slack thread.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
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

**State Enum Values:**

- `IDLE`
- `WAITING_FOR_INPUTS`
- `GENERATING_DEAL_ANALYSIS`
- `WAITING_FOR_APPROVAL`
- `GENERATING_DECK`
- `DONE`
- `ERROR`

### 21.2 Document Metadata

Metadata for created documents (optional, for auditing).

| Field | Type | Description |
| --- | --- | --- |
| doc_id | string | Google Doc/Slides ID |
| doc_type | enum | "deal_analysis" or "proposal_deck" |
| thread_ts | string | Originating Slack thread |
| client_name | string | Client name |
| created_by_user_id | string | Slack user who requested |
| created_at | timestamp | Creation timestamp |
| web_link | string | Shareable link |
| word_count | integer | Approximate word count (for Deal Analysis) |
| slide_count | integer | Number of slides (for Proposal Deck) |

### 21.3 Storage Implementation

For MVP, use simple JSON file storage:

```
data/
├── threads/
│   └── {channel_id}_{thread_ts}.json
└── documents/
    └── {doc_id}.json
```

\[TBD - needs product decision\]: Consider upgrading to SQLite or Redis for production if concurrent access becomes an issue.

---

## 22) Testing Strategy

### 22.1 Unit Tests

| Module | Test Focus | Example Test Cases |
| --- | --- | --- |
| `state/machine.py` | State transitions | Valid: IDLE → GENERATING_DEAL_ANALYSIS; Invalid: IDLE → GENERATING_DECK |
| `state/storage.py` | CRUD operations | Create, read, update thread state; Handle missing thread |
| `llm/context_builder.py` | Context assembly | Transcript truncation; Reference summarization; Token counting |
| `utils/parsing.py` | Transcript parsing | Extract client name; Handle empty file; Handle malformed markdown |
| `utils/validation.py` | Input validation | Valid .md file; Empty file detection; Size limits |
| `slack/messages.py` | Message formatting | Missing info list; Document links; Error messages |
| `drive/folders.py` | Folder logic | Path resolution; Name sanitization |

**Coverage Target:** &gt; 80% for core modules

### 22.2 Integration Tests

| Test Scenario | Components Involved | Verification |
| --- | --- | --- |
| Slack event → State update | Slack handlers, State machine | State correctly transitions |
| State → Drive folder creation | State machine, Drive client | Folder exists with correct structure |
| LLM call with mock response | LLM client, Context builder | Response parsed correctly |
| Full Deal Analysis flow | All except LLM (mocked) | Doc created, link returned, state = WAITING_FOR_APPROVAL |
| Full Deck flow | All except LLM (mocked) | Deck created from template, state = DONE |

**Mocking Strategy:**

- Mock Slack API with `slack_sdk.web.WebClient` stubs
- Mock Google APIs with `unittest.mock` or `responses` library
- Mock LLM with predefined response fixtures

### 22.3 End-to-End Tests

| Scenario | Steps | Expected Outcome |
| --- | --- | --- |
| Happy path - full flow | Attach transcript → "Analyse" → "Yes" | Deal Analysis + Proposal Deck created |
| Rejection path | Attach transcript → "Analyse" → "No" | Only Deal Analysis created, bot stops |
| Updated Deal Analysis | Attach transcript → "Analyse" → attach updated doc → "Use this" | Deck uses updated content |
| Missing transcript | "Analyse" (no attachment) | Error message, stays IDLE |
| Empty transcript | Attach empty .md → "Analyse" | Error message, stays IDLE |
| LLM timeout + retry | Simulate LLM timeout | Retries 3x, then ERROR state |
| Recovery after error | ERROR state → user retries | Successful completion |
| Multiple reference files | Attach transcript + 3 references | All references included in context |

### 22.4 Test Environment

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

### 22.5 Test Fixtures

Store test fixtures in `tests/fixtures/`:

```
tests/
├── fixtures/
│   ├── transcripts/
│   │   ├── valid_transcript.md
│   │   ├── empty_transcript.md
│   │   └── long_transcript.md (>16K tokens)
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

## 23) Rollout Plan

### Phase 1: Internal Alpha (Week 1-2)

| Activity | Details |
| --- | --- |
| Deployment | Deploy to dedicated test Slack channel: `#proposal-assistant-alpha` |
| Users | 2-3 internal developers + 1 sales team member |
| Monitoring | Manual review of ALL interactions |
| Data | Use test client folders only (not real client data) |
| Goal | Validate core flow works end-to-end |
| Exit Criteria | 10 successful full flows with no critical bugs |

### Phase 2: Limited Beta (Week 3-4)

| Activity | Details |
| --- | --- |
| Deployment | Enable in main Slack workspace, invite-only |
| Users | 5-10 consultants/salespeople (early adopters) |
| Monitoring | Daily review of error logs; Weekly feedback sync |
| Data | Real client data with extra oversight |
| Goal | Validate quality of outputs; Gather UX feedback |
| Feedback | Slack survey after each use (thumbs up/down + optional comment) |
| Exit Criteria | &gt; 80% positive feedback; &lt; 5% error rate |

### Phase 3: General Availability (Week 5-6)

| Activity | Details |
| --- | --- |
| Deployment | Announce in `#general`; Add to company tooling docs |
| Users | All Renessai consultants and salespeople |
| Monitoring | Automated alerting on error rate spike |
| Documentation | User guide; FAQ; Troubleshooting guide |
| Support | Designated point of contact for issues |
| Goal | Full adoption for new proposal workflows |

### Phase 4: Optimization (Ongoing)

| Activity | Details |
| --- | --- |
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

## 24) Known TBDs (Require Product Decision)

Items explicitly flagged as needing product/engineering decisions:

| Item | Context | Default Assumption |
| --- | --- | --- |
| Default `num_ctx` for Ollama | Section 12 - Token management | 32768 for dev; TBD for prod based on hardware |
| Maximum transcript size | Before chunking/summarization required | 16K tokens (\~12K words) |
| Retry limit for LLM calls | Error handling | 3 retries with exponential backoff |
| State storage backend | JSON files vs SQLite vs Redis | JSON files for MVP |
| Support SLA | Response time for user issues | Best-effort during beta |
| Feedback mechanism | How to collect user ratings | Slack reactions or survey |
| Audit log retention | How long to keep logs | 90 days |
| Multi-language support | Transcripts in non-English | English only for MVP |
| Concurrent request handling | Queue vs parallel processing | Sequential for MVP |
| Template versioning | How to handle template updates | Manual update, notify users |

---

## 25) Dependencies & External Services

### 25.1 External Services

| Service | Purpose | Failure Impact |
| --- | --- | --- |
| Slack API | Receive messages, send responses | Bot non-functional |
| Google Drive API | Store/retrieve files | Cannot access inputs or save outputs |
| Google Docs API | Create Deal Analysis | Cannot generate Deal Analysis |
| Google Slides API | Create Proposal Deck | Cannot generate Proposal Deck |
| Ollama (local) | LLM inference | Cannot generate content |

### 25.2 Python Dependencies

```toml
# pyproject.toml dependencies
[project]
dependencies = [
    "slack-bolt>=1.18.0",
    "google-api-python-client>=2.100.0",
    "google-auth>=2.23.0",
    "openai>=1.0.0",  # For Ollama OpenAI-compatible API
    "python-dotenv>=1.0.0",  # Optional, for local dev
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

### 25.3 Infrastructure Requirements

| Component | Requirement |
| --- | --- |
| Python | 3.12+ |
| Ollama | Latest stable, with qwen2.5:14b model pulled |
| RAM | 16GB minimum (32GB recommended for 14B model) |
| GPU | Optional but recommended (NVIDIA with CUDA for faster inference) |
| Network | Outbound HTTPS to Slack and Google APIs |

---

## 26) Proposal Template Specification (Google Slides / PowerPoint)

This section defines the exact template structure the bot must use when creating Proposal Decks.

### 26.1 Template Metadata

| Property | Value |
| --- | --- |
| Template name | Renessai basic template 10_2025.pptx |
| Slide dimensions | 10.0" × 5.62" (16:9 widescreen) |
| Total slide masters | 2 |
| Template location | `Drive / Templates / Renessai Proposal Template` |
| Environment variable | `PROPOSAL_TEMPLATE_SLIDE_ID` |

### 26.2 Brand Color Theme (Renessai)

Use **Theme 3 - Simple Light Green** as the primary brand theme:

| Color Role | Hex Code | Usage |
| --- | --- | --- |
| dark1 | `#081F09` | Primary text |
| light1 | `#FFFFFF` | Primary background |
| dark2 | `#244231` | Secondary text / headers |
| light2 | `#D6D1CA` | Secondary background / subtle fills |
| accent1 | `#EAFF01` | Primary accent (Renessai yellow-green) |
| accent2 | `#0D1F08` | Dark accent |
| accent3 | `#BBF92B` | Highlight / call-to-action |
| accent4 | `#7EBC00` | Success / positive indicators |
| accent5 | `#346D55` | Muted green accent |
| accent6 | `#264634` | Dark green accent |
| hyperlink | `#7EBC00` | Link color |

**Rule:** Do NOT override these colors programmatically. Use theme color references, not hardcoded hex values.

### 26.3 Typography

| Element | Font | Size | Weight |
| --- | --- | --- | --- |
| Titles | Arial | 14pt | Regular |
| Body text (all levels) | Arial | 14pt | Regular |
| Headings | Arial | 14pt | Regular |

**Rule:** Do NOT change fonts or sizes. Content must fit within placeholder bounds; if too long, split across slides rather than shrinking text.

### 26.4 Available Slide Layouts

| Layout Name | Placeholders | Best Used For |
| --- | --- | --- |
| `TITLE` | CENTER_TITLE (idx=0), SUBTITLE (idx=1), SLIDE_NUMBER (idx=12) | Cover page (Slide 1) |
| `SECTION_HEADER` | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Section dividers |
| `TITLE_AND_BODY` | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Standard content slides |
| `TITLE_AND_TWO_COLUMNS` | TITLE (idx=0), BODY (idx=1), BODY (idx=2), SLIDE_NUMBER (idx=12) | Comparison / side-by-side |
| `TITLE_ONLY` | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Custom content slides |
| `ONE_COLUMN_TEXT` | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Narrow text with image space |
| `MAIN_POINT` | TITLE (idx=0), SLIDE_NUMBER (idx=12) | Key takeaway / quote slides |
| `SECTION_TITLE_AND_DESCRIPTION` | TITLE (idx=0), SUBTITLE (idx=1), BODY (idx=2), SLIDE_NUMBER (idx=12) | Section intro with context |
| `CAPTION_ONLY` | BODY (idx=1), SLIDE_NUMBER (idx=12) | Image-heavy slides |
| `BIG_NUMBER` | TITLE (idx=0), BODY (idx=1), SLIDE_NUMBER (idx=12) | Metrics / KPI highlights |
| `BLANK` | SLIDE_NUMBER (idx=12) | Fully custom slides |

### 26.5 Proposal Slide → Layout Mapping

This table maps each proposal slide (from Section 9) to the appropriate template layout:

| Slide # | Title | Layout to Use | Placeholder Mapping |
| --- | --- | --- | --- |
| 1 | Cover Page | `TITLE` | CENTER_TITLE: "\[Client\] x Renessai – \[Project\]", SUBTITLE: "Prepared for: \[Contact\] | Date: \[Date\]" |
| 2 | Executive Summary | `TITLE_AND_BODY` | TITLE: "Executive Summary", BODY: Situation + stakes + outcomes |
| 3 | Client Context & Objectives | `TITLE_AND_TWO_COLUMNS` | TITLE: "Client Context & Objectives", BODY(1): Current state, BODY(2): Desired state |
| 4 | Challenges & Business Impact | `TITLE_AND_BODY` | TITLE: "Challenges & Business Impact", BODY: Problems + risks + impact |
| 5 | Renessai Proposed Solution — Overview | `SECTION_TITLE_AND_DESCRIPTION` | TITLE: "Proposed Solution", SUBTITLE: High-level summary, BODY: Key capabilities |
| 6 | Detailed Solution & Scope | `TITLE_AND_BODY` | TITLE: "Solution Details & Scope", BODY: Must-haves, nice-to-haves, matching capabilities |
| 7 | Implementation Approach & Timeline | `TITLE_AND_TWO_COLUMNS` | TITLE: "Implementation Approach", BODY(1): Phases, BODY(2): Timeline |
| 8 | Value Case / Expected Outcomes | `BIG_NUMBER` | TITLE: Key metric/outcome number, BODY: Supporting context |
| 9 | Commercials & Terms | `TITLE_AND_BODY` | TITLE: "Investment & Terms", BODY: Budget, pricing, terms |
| 10 | Risk Mitigation & Assurance | `TITLE_AND_TWO_COLUMNS` | TITLE: "Risk Mitigation", BODY(1): Risks, BODY(2): Mitigations |
| 11 | Proof of Success (Case Studies) | `TITLE_AND_BODY` | TITLE: "Proven Results", BODY: Case study summaries |
| 12 | Next Steps | `TITLE_AND_BODY` | TITLE: "Next Steps", BODY: Action items with owners and dates |
| 13 | Company Intro | `TITLE_AND_BODY` | *Standard slide - auto-appended from template* |
| 14 | Team Bios | `TITLE_AND_BODY` | *Standard slide - auto-appended from template* |
| 15 | Contact Info | `TITLE` | *Standard slide - auto-appended from template* |

### 26.6 Placeholder Position Reference (inches)

For programmatic slide population, use these exact positions:

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

### 26.7 Full Template JSON (Reference)

Store this in `config/proposal_template_spec.json` for programmatic access:

```json
{
  "template_name": "Renessai basic template 10_2025.pptx",
  "presentation_settings": {
    "slide_width_inches": 10.0,
    "slide_height_inches": 5.62,
    "aspect_ratio": "16:9 (widescreen)",
    "total_slide_masters": 2,
    "total_slides": 7
  },
  "brand_theme": "Simple Light Green (Theme 3 - Renessai Brand)",
  "colors": {
    "dark1": "#081F09",
    "light1": "#FFFFFF",
    "dark2": "#244231",
    "light2": "#D6D1CA",
    "accent1": "#EAFF01",
    "accent2": "#0D1F08",
    "accent3": "#BBF92B",
    "accent4": "#7EBC00",
    "accent5": "#346D55",
    "accent6": "#264634",
    "hyperlink": "#7EBC00",
    "followed_hyperlink": "#0097A7"
  },
  "typography": {
    "font_scheme": "Office",
    "heading_font": "Arial",
    "body_font": "Arial",
    "default_size_pt": 14.0
  },
  "slide_layouts": [
    {"name": "TITLE", "placeholders": [
      {"idx": 0, "type": "CENTER_TITLE", "position": {"left": 0.34, "top": 0.81, "width": 9.32, "height": 2.24}},
      {"idx": 1, "type": "SUBTITLE", "position": {"left": 0.34, "top": 3.1, "width": 9.32, "height": 0.87}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "SECTION_HEADER", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 2.35, "width": 9.32, "height": 0.92}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "TITLE_AND_BODY", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 0.49, "width": 9.32, "height": 0.63}},
      {"idx": 1, "type": "BODY", "position": {"left": 0.34, "top": 1.26, "width": 9.32, "height": 3.74}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "TITLE_AND_TWO_COLUMNS", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 0.49, "width": 9.32, "height": 0.63}},
      {"idx": 1, "type": "BODY", "position": {"left": 0.34, "top": 1.26, "width": 4.37, "height": 3.74}},
      {"idx": 2, "type": "BODY", "position": {"left": 5.28, "top": 1.26, "width": 4.37, "height": 3.74}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "TITLE_ONLY", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 0.49, "width": 9.32, "height": 0.63}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "ONE_COLUMN_TEXT", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 0.61, "width": 3.07, "height": 0.83}},
      {"idx": 1, "type": "BODY", "position": {"left": 0.34, "top": 1.52, "width": 3.07, "height": 3.48}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "MAIN_POINT", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.54, "top": 0.49, "width": 6.96, "height": 4.47}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "SECTION_TITLE_AND_DESCRIPTION", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.29, "top": 1.35, "width": 4.42, "height": 1.62}},
      {"idx": 1, "type": "SUBTITLE", "position": {"left": 0.29, "top": 3.07, "width": 4.42, "height": 1.35}},
      {"idx": 2, "type": "BODY", "position": {"left": 5.4, "top": 0.79, "width": 4.2, "height": 4.04}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "CAPTION_ONLY", "placeholders": [
      {"idx": 1, "type": "BODY", "position": {"left": 0.34, "top": 4.63, "width": 6.56, "height": 0.66}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "BIG_NUMBER", "placeholders": [
      {"idx": 0, "type": "TITLE", "position": {"left": 0.34, "top": 1.21, "width": 9.32, "height": 2.15}},
      {"idx": 1, "type": "BODY", "position": {"left": 0.34, "top": 3.45, "width": 9.32, "height": 1.42}},
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]},
    {"name": "BLANK", "placeholders": [
      {"idx": 12, "type": "SLIDE_NUMBER", "position": {"left": 9.27, "top": 5.1, "width": 0.6, "height": 0.43}}
    ]}
  ]
}
```

### 26.8 Slides Module Implementation Notes

When implementing the Slides module (`src/proposal_assistant/slides/`):

1. **Template Duplication:** Always duplicate the template; never modify the original.
2. **Layout Selection:** Use `get_layout_by_name(layout_name)` to select the correct layout.
3. **Placeholder Access:** Access placeholders by `idx`, not by position.
4. **Content Fitting:**
   - If text exceeds placeholder bounds, split into multiple slides.
   - Do NOT shrink font size below 14pt.
   - Do NOT change fonts from Arial.
5. **Color References:** Use theme color references (e.g., `scheme_color='ACCENT_1'`), not hex values.
6. **Standard Slides:** Slides 13-15 are pre-built in the template; do not regenerate them.