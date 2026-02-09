# [CLAUDE.md](http://CLAUDE.md) — Proposal Assistant

This is the instruction file for Claude Code. Read this file first before doing anything.

---

## 0. Quick Reference for Claude Code

**Audience.** This file is for Claude Code / coding assistants working inside this repo. It tells you how to structure changes, which LLM stack to use, and which other docs are the product source of truth.

**When in doubt:**

- For *product behavior* (what the bot should do, user flows, templates), defer to `project-context.md` and `prd.md`.
- For *architecture & implementation details*, defer to `technical-design.md`.
- For *ops, deployment, and production infra* (which still describe the older Ollama-based stack), defer to `ops-and-deployment.md` / `gcp-production-setup.md`, but treat **this [CLAUDE.md](http://CLAUDE.md) as the source of truth for the current LLM integration and code you write going forward**.

### 0.1 Core Commands (local dev)

```bash
# Install dependencies (dev + prod)
uv sync

# Install only production dependencies
uv sync --no-dev

# Run the bot
uv run python -m proposal_assistant.main

# Tests
uv run pytest                                # all tests
uv run pytest tests/unit/ -v                 # unit tests only
uv run pytest tests/integration/ -v          # integration tests only
uv run pytest --cov=src/proposal_assistant \
           --cov-report=html                # coverage report

# Lint, format, type check
uv run ruff check src/
uv run black src/
uv run pyright src/

# Docker (dev)
docker compose -f docker-compose.dev.yml up -d
```

---

## 1. Project Overview

**Proposal Assistant** is a Slack bot used by Renessai consultants and salespeople. It transforms meeting transcripts into two draft outputs:

1. **Deal Analysis** — a structured Google Doc summarizing client discovery findings
2. **Proposal Deck** — a Google Slides presentation following Renessai's standard template

The bot enforces a **two-step workflow** with a hard approval gate between Deal Analysis and Proposal Deck. Outputs must be grounded in real inputs — never invent facts.

---

## 2. Architecture Decision: Claude Agent SDK (NOT Ollama)

**CRITICAL:** This project uses the **Claude Agent SDK** (`claude-agent-sdk >= 0.1.33`) as the primary LLM backend. **NOT** Ollama, **NOT** a local model, **NOT** the OpenAI-compatible API.

### What This Means

- **No GPU required.** No NVIDIA drivers, no CUDA, no `ollama` container.
- **No** `OLLAMA_*` **environment variables.** Remove all references. Use `ANTHROPIC_API_KEY` instead.
- **No OpenAI-compatible client.** Do NOT use the `openai` Python package for LLM calls.
- **Use** `claude_agent_sdk` **imports**: `query`, `ClaudeSDKClient`, `ClaudeAgentOptions`, `tool`, `create_sdk_mcp_server`, `HookMatcher`, `HookContext`.
- **Custom tools via MCP.** Google Drive/Docs/Slides operations are defined as `@tool` decorated Python functions, registered as in-process MCP servers.
- **Context management is automatic.** The SDK handles compaction and context overflow — no manual token counting or truncation.
- **Single container deployment.** Docker Compose runs ONE container (the bot). No Ollama sidecar.
- **Auth:** `ANTHROPIC_API_KEY` environment variable. Get it from [console.anthropic.com](http://console.anthropic.com).
- **Model:** `claude-sonnet-4-5-20250514` (Claude Sonnet 4.5)

### SDK Installation

```bash
uv add claude-agent-sdk>=0.1.33
```

The Claude Code CLI is automatically bundled with the package — no separate installation required.

### What This Replaces

The original project documents (`project-context.md`, `prd.md`, `technical-design.md`, `ops-and-deployment.md`, `gcp-production-setup.md`, `README.md`) all describe an **Ollama + qwen2.5:14b** stack accessed via the `openai` Python SDK. That stack is obsolete for new code. If you see references to `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `openai.OpenAI(...)`, or `qwen2.5:14b` in those docs, **ignore them** and use the patterns in this file instead.

---

## 3. Tech Stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Language | Python 3.12 | Modern syntax (type hints, `match`, `|` union) |
| Package manager | uv | All commands use `uv run`. Never use `pip` directly. |
| Slack SDK | slack-bolt &gt;= 1.18.0 | Socket Mode for event handling |
| Google APIs | google-api-python-client &gt;= 2.100.0 | Service account auth only |
| **LLM SDK** | **claude-agent-sdk &gt;= 0.1.33** | **Claude Agent SDK with custom MCP tools** |
| **LLM model** | **Claude Sonnet 4.5** (`claude-sonnet-4-5-20250514`) | **Cloud inference. No local model.** |
| **Auth** | **ANTHROPIC_API_KEY** | **API key from [console.anthropic.com](http://console.anthropic.com)** |
| Testing | pytest, pytest-cov, pytest-asyncio | Coverage target: &gt;80% for core modules (state, LLM, Drive) |
| Linting | ruff | Must pass with zero warnings |
| Formatting | black | Line length **100**. Must pass `black --check` |
| Type checking | pyright | Strict mode recommended |
| Build system | hatchling | Wheel packages `src/proposal_assistant` |
| State storage | JSON files (MVP) | Path: `data/threads/`, `data/documents/` |

---

## 4. Repository Structure

```
src/proposal_assistant/
├── __init__.py
├── main.py                    # Entry point — initializes Bolt app
├── config.py                  # Env var loading, Config dataclass
├── health.py                  # Health check module (Claude API, Drive, storage)
│
├── slack/
│   ├── __init__.py
│   ├── handlers.py            # Message/event handlers (Analyse, Yes/No, Regenerate)
│   ├── commands.py            # Slash commands (/pa-status)
│   └── messages.py            # Block message formatters, error templates
│
├── drive/
│   ├── __init__.py
│   ├── client.py              # Google Drive API wrapper
│   ├── folders.py             # Folder navigation, creation, resolution
│   └── permissions.py         # File sharing, access management
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
│   ├── agent.py               # Claude Agent SDK client wrapper
│   ├── tools.py               # MCP tool definitions (@tool decorated functions)
│   ├── mcp_server.py          # create_sdk_mcp_server setup
│   ├── hooks.py               # Pre/post tool-use hooks (security, logging)
│   ├── context_builder.py     # Assembles context from transcript + refs + web
│   └── prompts/
│       ├── __init__.py
│       ├── system_sales_advisor.txt
│       ├── deal_analysis.py
│       ├── proposal_deck.py
│       └── missing_info_detector.txt
│
├── state/
│   ├── __init__.py
│   ├── models.py              # State, Event enums + ThreadState dataclass
│   ├── machine.py             # State machine transitions + guards
│   └── storage.py             # JSON file persistence (MVP)
│
├── web/
│   ├── __init__.py
│   └── fetcher.py             # URL content fetching
│
└── utils/
    ├── __init__.py
    ├── parsing.py             # Transcript/markdown parsing
    ├── validation.py          # Input validation helpers
    ├── logging.py             # Structured JSON logger
    └── alerts.py              # Slack alerting utility
```

**Do NOT create files outside this structure unless explicitly asked.**

### 4.1 Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `slack/` | Slack Bolt event handlers, Block Kit message builders. `handlers.py` orchestrates the workflow by calling into other modules. |
| `llm/` | LLM interaction via Claude Agent SDK. `agent.py` wraps `ClaudeSDKClient`. `tools.py` defines MCP tools for Google API operations. Prompt templates live in `llm/prompts/`. |
| `drive/` | Google Drive API: folder creation (`folders.py`), file permissions (`permissions.py`), and API wrapper (`client.py`). |
| `docs/` | Google Docs API: creates Deal Analysis documents from LLM-structured JSON (`deal_analysis.py`). |
| `slides/` | Google Slides API: copies a template deck and populates placeholders with LLM-generated content (`proposal_deck.py`). 12-slide proposal structure: `slide_1_cover` through `slide_12_next_steps`. |
| `state/` | State machine (`machine.py`), state/event enums and `ThreadState` model (`models.py`), JSON persistence (`storage.py`). |
| `web/` | URL content fetcher for supplementary web research. |
| `config.py` | Singleton `Config` dataclass loaded from env vars via `@classmethod from_env()`. |

### 4.2 Key Differences from Original Structure

| Old File (Ollama era) | New File | What Changed |
| --- | --- | --- |
| `llm/client.py` | `llm/agent.py` | Replaced `openai.OpenAI(...)` with `ClaudeSDKClient` wrapper |
| — | `llm/tools.py` | **New.** `@tool` decorated functions for Drive/Docs/Slides operations |
| — | `llm/mcp_server.py` | **New.** `create_sdk_mcp_server()` setup bundling all custom tools |
| — | `llm/hooks.py` | **New.** Pre-tool-use security hooks (block dangerous commands, log tool usage) |
| `health.py` (`check_ollama()`) | `health.py` (`check_claude_api()`) | Replaced Ollama health check with Anthropic API connectivity check |

---

## 5. Claude Agent SDK Integration Patterns

> **Full code examples** for every pattern below live in `CODING_INSTRUCTIONS.md` §4. This section is an overview — refer there for copy-pasteable implementations.

### 5.1 Core Imports

```python
from claude_agent_sdk import (
    query,                    # One-shot async query
    ClaudeSDKClient,          # Session-based client with custom tools
    ClaudeAgentOptions,       # Configuration options
    tool,                     # @tool decorator for custom MCP tools
    create_sdk_mcp_server,    # Bundle tools into in-process MCP server
    AssistantMessage,         # Response message type
    ResultMessage,            # Final result message
    HookMatcher,              # Hook filtering
    HookContext,              # Hook context
)
from claude_agent_sdk.types import TextBlock, ToolUseBlock
```

### 5.2 One-Shot Query (Simple Usage)

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def simple_generation(prompt: str) -> str:
    options = ClaudeAgentOptions(
        system_prompt="You are a senior sales advisor...",
        permission_mode="acceptEdits",
    )
    result = ""
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, "result"):
            result = message.result
    return result
```

### 5.3 Custom MCP Tools Pattern

Define each Google API operation as a `@tool` decorated async function in `llm/tools.py`. Example:

```python
from claude_agent_sdk import tool
from typing import Any

@tool(
    "create_client_folder",
    "Create or get existing client folder structure in Google Drive",
    {"client_name": str}
)
async def create_client_folder(args: dict[str, Any]) -> dict[str, Any]:
    from proposal_assistant.drive.client import DriveClient
    drive = DriveClient()
    folder_ids = drive.get_or_create_client_folder(args["client_name"])
    return {
        "content": [{"type": "text", "text": f"Client folder created: {folder_ids}"}]
    }
```

See `CODING_INSTRUCTIONS.md` §4.2 for all four tool definitions (`create_client_folder`, `create_deal_analysis`, `create_proposal_deck`, `share_document`).

### 5.4 MCP Server Setup

```python
# src/proposal_assistant/llm/mcp_server.py
from claude_agent_sdk import create_sdk_mcp_server
from proposal_assistant.llm.tools import (
    create_client_folder, create_deal_analysis,
    create_proposal_deck, share_document,
)

def get_proposal_mcp_server():
    return create_sdk_mcp_server(
        name="proposal-assistant",
        version="1.0.0",
        tools=[create_client_folder, create_deal_analysis,
               create_proposal_deck, share_document],
    )
```

### 5.5 Agent Client Wrapper

See `CODING_INSTRUCTIONS.md` §4.4 for the full `llm/agent.py` implementation. Key functions:

- `get_agent_options(allowed_tools, max_turns)` → `ClaudeAgentOptions`
- `generate_deal_analysis(transcript, context)` → `str`
- `generate_proposal_content(deal_analysis)` → `str`

### 5.6 LLM Response Handling

The LLM returns structured JSON for Deal Analysis and Proposal Deck content. The response is wrapped in markdown code fences. Use a `_extract_json()` helper to parse:

```python
import json
import re

def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Try to find JSON in code blocks first
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Fall back to parsing the entire response
    return json.loads(text)
```

Expected return shapes:

```python
# Deal Analysis
{
    "content": {
        "opportunity_snapshot": {...},
        "problem_impact": {...},
        "current_desired_state": {...},
        "buying_dynamics": {...},
        "renessai_fit": {...},
        "proof_next_actions": {...},
    },
    "missing_info": ["Budget range", "Decision timeline", ...],
    "raw_response": str,  # For debugging
}

# Proposal Deck
{
    "slides": [
        {"slide_1_cover": {...}},
        {"slide_2_executive_summary": {...}},
        ...
        {"slide_12_next_steps": {...}},
    ],
    "raw_response": str,
}
```

### 5.7 Security Hooks

See `CODING_INSTRUCTIONS.md` §4.5 for the full hooks implementation. Key hooks:

- `log_tool_usage` — audit log every MCP tool invocation
- `block_dangerous_operations` — deny `rm -rf`, `sudo`, `chmod 777`, `curl | sh`

---

## 6. Environment Variables

> **Important:** The original project docs list `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, `OPENAI_API_KEY` as required/optional. Those are **removed**. The canonical list is below.

### Required

```bash
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...

# Google (Service Account)
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
GOOGLE_DRIVE_ROOT_FOLDER_ID=1ABC...

# Templates
PROPOSAL_TEMPLATE_SLIDE_ID=1XYZ...

# LLM — Claude Agent SDK
ANTHROPIC_API_KEY=sk-ant-...
```

### Optional

```bash
LOG_LEVEL=INFO
ENVIRONMENT=development   # or "staging", "production"

# Alerting
SLACK_ALERT_CHANNEL=#proposal-assistant-alerts

# Feature flags
BOT_ENABLED=true
```

### Removed (do NOT use)

```bash
# REMOVED — from the Ollama architecture, do not use:
# OLLAMA_BASE_URL
# OLLAMA_MODEL
# OLLAMA_NUM_CTX
# OLLAMA_API_KEY
# OPENAI_API_KEY (not needed — we use ANTHROPIC_API_KEY)
```

---

## 7. Config Dataclass

```python
# src/proposal_assistant/config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    # Slack
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str

    # Google
    google_service_account_json: str
    google_drive_root_folder_id: str

    # Templates
    proposal_template_slide_id: str

    # LLM — Claude Agent SDK
    anthropic_api_key: str

    # App settings
    log_level: str = "INFO"
    environment: str = "development"
    bot_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
            slack_app_token=os.environ["SLACK_APP_TOKEN"],
            slack_signing_secret=os.environ["SLACK_SIGNING_SECRET"],
            google_service_account_json=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            google_drive_root_folder_id=os.environ["GOOGLE_DRIVE_ROOT_FOLDER_ID"],
            proposal_template_slide_id=os.environ["PROPOSAL_TEMPLATE_SLIDE_ID"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            environment=os.getenv("ENVIRONMENT", "development"),
            bot_enabled=os.getenv("BOT_ENABLED", "true").lower() == "true",
        )
```

---

## 8. Health Check (Updated for Claude SDK)

```python
# src/proposal_assistant/health.py
import os, json, time, httpx
from pathlib import Path

def check_claude_api() -> dict:
    """Check if Claude API is reachable."""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        resp = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "healthy", "provider": "anthropic"}
        return {"status": "degraded", "status_code": resp.status_code}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def check_google_drive() -> dict:
    """Check if Google Drive API is accessible."""
    try:
        from proposal_assistant.drive.client import DriveClient
        client = DriveClient()
        root_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")
        client.find_folder(root_id, "_health_check_probe")
        return {"status": "healthy", "root_folder": root_id}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def check_state_storage() -> dict:
    """Check if state storage directory is writable."""
    try:
        data_dir = Path("data/threads")
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / "_health_check.json"
        test_file.write_text(json.dumps({"ts": time.time()}))
        test_file.unlink()
        return {"status": "healthy", "path": str(data_dir)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def check() -> dict:
    """Run all health checks. Used by Docker HEALTHCHECK."""
    results = {
        "claude_api": check_claude_api(),
        "google_drive": check_google_drive(),
        "state_storage": check_state_storage(),
        "timestamp": time.time(),
    }
    all_healthy = all(
        r["status"] == "healthy"
        for r in results.values()
        if isinstance(r, dict) and "status" in r
    )
    if not all_healthy:
        raise SystemExit(1)
    return results
```

---

## 9. Docker (Single Container — No Ollama)

### Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

# Install Node.js 18+ (required by Claude Agent SDK CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen
COPY src/ src/
COPY config/ config/
RUN mkdir -p data/threads data/documents logs

# Non-root user
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app
USER botuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "from proposal_assistant.health import check; check()" || exit 1

CMD ["uv", "run", "python", "-m", "proposal_assistant.main"]
```

### docker-compose.yml (Production)

```yaml
version: "3.9"
services:
  proposal-assistant:
    build: .
    container_name: proposal-assistant
    restart: unless-stopped
    env_file: .env
    environment:
      - ENVIRONMENT=production
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    networks:
      - internal
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
    # No ports — Socket Mode is outbound only
    # No Ollama sidecar — Claude Agent SDK uses cloud API

networks:
  internal:
    driver: bridge
```

### docker-compose.dev.yml

```yaml
version: "3.9"
services:
  proposal-assistant:
    build: .
    container_name: proposal-assistant-dev
    env_file: .env
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
    volumes:
      - ./src:/app/src          # Hot-reload source
      - ./data:/app/data
      - ./logs:/app/logs
    networks:
      - internal

networks:
  internal:
    driver: bridge
```

---

## 10. pyproject.toml

```toml
[project]
name = "proposal-assistant"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "slack-bolt>=1.18.0",
    "google-api-python-client>=2.100.0",
    "google-auth>=2.23.0",
    "claude-agent-sdk>=0.1.33",
    "httpx>=0.27.0",
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

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.black]
target-version = ["py312"]
line-length = 100

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 11. State Machine

### States

```
IDLE → GENERATING_DEAL_ANALYSIS → WAITING_FOR_APPROVAL → GENERATING_DECK → DONE
  ↓                                       ↓
WAITING_FOR_INPUTS                      DONE (rejected)

Any state → ERROR (on failure)
ERROR → GENERATING_DEAL_ANALYSIS (on retry)
```

### Transition Rules

```python
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

### Guards

- If transcript missing/empty → `WAITING_FOR_INPUTS` (do not proceed)
- Always create Deal Analysis before asking for approval
- Only enter `GENERATING_DECK` after approval ("Yes") OR updated Deal Analysis provided
- Threads stay in `WAITING_FOR_APPROVAL` indefinitely — **no timeout, no auto-close** (see `prd.md` §FR-STATE-009)

---

## 12. Workflow (End-to-End)

 1. User uploads `.md` transcript + types "Analyse" in Slack
 2. Bot acknowledges within 3 seconds (NFR-PERF-001)
 3. Bot extracts client name, creates Drive folder structure under `/Clients/{ClientName}/`
 4. Bot sends transcript + context to Claude Agent SDK → generates Deal Analysis
 5. Bot creates Google Doc with Deal Analysis content in the `Analyse here/` folder
 6. Bot shares doc with channel members as Editor
 7. Bot posts in thread: doc link + missing info list + interactive approval buttons (Yes/No)
 8. User clicks **Yes** → bot generates proposal content via Claude SDK
 9. Bot duplicates Slides template (never modifies original), populates slides
10. Bot shares deck with channel members
11. Bot posts deck link — **DONE**

### Alternative Paths

- **User replies "No"** → bot stops gracefully, Deal Analysis stays in Drive, workflow ends
- **User uploads an updated Deal Analysis** → bot uses the updated version for deck generation
- **User says "Regenerate"** → bot creates a new versioned Deal Analysis (v2, v3…) as a separate doc; original stays for reference

---

## 13. Performance Targets

From `prd.md` §5.1 — these are your non-functional requirements:

| Metric | Target | Notes |
| --- | --- | --- |
| Slack acknowledgment | &lt; 3 seconds | React/reply quickly to show bot is working |
| Deal Analysis generation | &lt; 60 seconds | End-to-end from inputs received to doc created |
| Proposal Deck generation | &lt; 120 seconds | Includes template duplication + content population |
| Concurrent users | 5 simultaneous | Based on team size |
| Error rate | &lt; 5% | Requests resulting in ERROR state |

---

## 14. Error Handling

### Retry Strategy

- **LLM errors:** 3 retries with exponential backoff (1s, 2s, 4s)
- **Drive/Docs/Slides API errors:** 3 retries with exponential backoff
- **After max retries:** notify user with friendly message, set ERROR state, log alert

### Error Handling Matrix (Summary)

Full matrix in `prd.md` §8. Key error codes your code must handle:

| Error Code | Trigger | User Message |
| --- | --- | --- |
| `INPUT_MISSING` | No transcript attached | "Please attach a meeting transcript (.md file) to start." |
| `INPUT_INVALID` | Transcript empty/unreadable | "The transcript file appears to be empty or invalid." |
| `LANGUAGE_UNSUPPORTED` | Non-English transcript | "Only English transcripts are supported." |
| `LLM_ERROR` | Claude API error | "AI service temporarily unavailable. Please try again in a moment." |
| `LLM_INVALID` | Invalid/empty LLM response | "Unable to generate analysis. Please try again." |
| `DRIVE_PERMISSION` | Folder not accessible | "Unable to access the client folder." |
| `DOCS_ERROR` | Doc creation fails | "Failed to create the Deal Analysis document. Please try again." |
| `SLIDES_ERROR` | Deck creation fails | "Failed to create the proposal deck. Please try again." |
| `STATE_MISSING` | Thread state lost | "I've lost track of this conversation. Please start over with 'Analyse'." |
| `APPROVAL_UNCLEAR` | Unknown approval response | "Please reply 'Yes' to create the deck, or 'No' to stop." |

**Rule:** Never expose raw API errors. Always use the user messages above.

---

## 15. Key Product Rules (MUST FOLLOW)

1. **Grounded Content** — Use only provided inputs. Never invent facts. Flag missing info as "Unknown / Not provided".
2. **Two-Step Workflow** — Always generate Deal Analysis first. Proposal Deck only after explicit "Yes" or updated Deal Analysis.
3. **No Secret Logging** — Never log API keys, tokens, or full transcripts. Log only IDs, links, status codes.
4. **Template Integrity** — Never modify the original Slides template. Always duplicate. Never change fonts/colors/branding. All text Arial 14pt. Use theme color references (`scheme_color='ACCENT_1'`), not hardcoded hex.
5. **Drive Scoping** — Only write to `/Clients/{ClientName}/` folder structure. Never delete/overwrite existing client docs.
6. **Friendly Errors** — Never expose raw API errors. Always use the error messages from §14.
7. **Content Overflow** — If text exceeds placeholder bounds, split across slides. Do NOT shrink font size.
8. **Footer Disclaimer** — Add "Draft generated by Proposal Assistant. Review before use." to all Deal Analysis docs and slide decks.

---

## 16. GCP Production Setup (Simplified — No GPU)

Since we no longer need Ollama/GPU, production is significantly simpler:

| Component | Specification | Monthly Cost |
| --- | --- | --- |
| GCE VM | e2-standard-4 (4 vCPU, 16 GB RAM) | \~$100 |
| Boot disk | 30 GB SSD | \~$5 |
| Network | Outbound HTTPS only | \~$2 |
| Claude API | Pay-per-use (Anthropic) | Variable (\~$50-200 based on usage) |
| Google APIs | Free tier | $0 |
| **Total** |  | **\~$150-310/month** |

No GPU quota request needed. No NVIDIA drivers. No CUDA.

### VM Setup

```bash
gcloud compute instances create proposal-assistant-prod \
    --project=renessai-proposal-assistant \
    --zone=europe-north1-b \
    --machine-type=e2-standard-4 \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-ssd \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=proposal-assistant
```

---

## 17. CI/CD (GitHub Actions)

### CI (on push/PR)

```yaml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run ruff check src/
      - run: uv run black --check src/
      - run: uv run pyright src/

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --dev
      - run: uv run pytest tests/unit/ --cov=src/proposal_assistant --cov-report=xml -v
      - run: uv run pytest tests/integration/ -v
      - run: uv run pytest --cov=src/proposal_assistant --cov-fail-under=80

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t proposal-assistant:${{ github.sha }} .
```

### Deploy (on merge to main)

SSH into GCE VM → `git pull` → `docker compose down` → `docker compose build` → `docker compose up -d` → smoke test. Full deploy workflow in `ops-and-deployment.md` §3.2.

---

## 18. Testing Strategy

### Unit Tests

- Mock `claude_agent_sdk` with `unittest.mock`
- Mock Google APIs with `unittest.mock`
- Mock Slack API with stubs
- Test state machine transitions, context building, input validation, message formatting

### Integration Tests

- Test full Deal Analysis flow with mocked LLM
- Test full Deck flow with mocked LLM
- Test Drive folder creation with test folders
- Test Slides layout selection and placeholder population

### Test Fixtures

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

### Running Tests

```bash
uv run pytest                                      # All tests
uv run pytest tests/unit/ -v                       # Unit only
uv run pytest tests/integration/ -v                # Integration only
uv run pytest --cov=src/proposal_assistant --cov-report=html  # With coverage
```

---

## 19. Implementation Plan (Phases)

### Phase 1: Foundation (Week 1)

- F1: Config + environment (`config.py`, `.env.example`, `pyproject.toml`)
- F2: State machine core (models, transitions, JSON storage)
- F3: Slack event handling (`main.py`, handlers, file download)
- F4: Input validation (transcript validation, client name extraction, language detection)

### Phase 2: Core Integration (Week 2)

- F5: Drive folder operations (find/create client folders)
- F6: LLM context builder (assemble transcript + references)
- F7: Claude Agent SDK client wrapper (`agent.py`, `tools.py`, `mcp_server.py`, `hooks.py`)
- F8: Deal Analysis generation via Claude SDK

### Phase 3: Document Creation (Week 3)

- F9: Google Docs integration (create + populate Deal Analysis with template)
- F10: Missing info detection
- F11: Slack response formatting (blocks, buttons, links)
- F12: Approval gate (Yes/No interactive buttons, state transitions)

### Phase 4: Proposal Deck (Week 4)

- F13: Proposal deck content generation via Claude SDK
- F14: Google Slides integration (duplicate template, populate placeholders by `idx`)
- F15: File sharing/permissions (share with channel members as Editor)

### Phase 5: Enhanced Features (Week 5)

- F16: Multi-file support (merge multiple transcripts)
- F17: Updated Deal Analysis handling (user uploads revised doc)
- F18: Regeneration (versioning: v2, v3 — new doc, keep previous)
- F19: Web URL fetching
- F20: DM support (identical functionality to channels)

### Phase 6: Polish (Week 6)

- F22: Auto-chunking long transcripts (SDK handles context, but pre-chunk very large inputs if needed)
- E2E integration testing
- Production deployment
- Monitoring and alerting setup

---

## 20. DO NOT List (Strict Rules)

- Do NOT use `openai` Python package for LLM calls — use `claude_agent_sdk`
- Do NOT reference Ollama, `OLLAMA_*` env vars, or local models in new code
- Do NOT create a proposal deck unless user explicitly approves
- Do NOT invent facts — write "Unknown / Not provided" if missing
- Do NOT edit the original Slides template — always duplicate
- Do NOT change theme/fonts/colors/branding (Arial 14pt, theme colors only)
- Do NOT log secrets or full transcripts
- Do NOT refactor unrelated code
- Do NOT add dependencies unless necessary and explained
- Do NOT rename/move files unless required
- Do NOT write outside approved client folders
- Do NOT delete/overwrite client docs or decks
- Do NOT proceed on empty/broken transcript
- Do NOT shrink text to unreadable sizes — split slides instead
- Do NOT call LLM APIs without proper error handling and retry logic (3x, 1s/2s/4s backoff)
- Do NOT expose raw API errors to users — use the Error Handling Matrix
- Do NOT use hardcoded hex color values — use `scheme_color` theme references

---

## 21. Reference Documents

| Document | Purpose | LLM stack status |
| --- | --- | --- |
| `project-context.md` | Product context, workflows, templates, LLM integration | **Ollama-era** — ignore LLM sections |
| `prd.md` | Requirements, API contracts, data models, acceptance criteria | **Ollama-era** — LLM reqs outdated, everything else current |
| `technical-design.md` | Architecture, implementation plan, task breakdown, testing | **Ollama-era** — ignore LLM client details |
| `CODING_INSTRUCTIONS.md` | Detailed coding standards and Claude SDK patterns | **Updated for Claude SDK** |
| `ops-and-deployment.md` | CI/CD, Docker, monitoring, runbooks, scaling | **Ollama-era** — Docker/health sections outdated |
| `gcp-production-setup.md` | GCP provisioning, costs, security | **Ollama-era** — GPU/VM sections outdated |
| `README.md` | Developer setup and usage reference | **Ollama-era** — LLM setup outdated |
| `PROJECT_PLAN.md` | Generic project lifecycle template (Phase 0–15) | N/A — reference only |

---

## 22. Quick Start for Development

```bash
# 1. Clone and install
git clone <repo-url>
cd proposal-assistant-v1
uv sync

# 2. Configure
cp .env.example .env
# Edit .env — add SLACK_*, GOOGLE_*, ANTHROPIC_API_KEY, PROPOSAL_TEMPLATE_SLIDE_ID

# 3. Verify Claude API access
python -c "import httpx; print(httpx.get('https://api.anthropic.com/v1/models', headers={'x-api-key': 'YOUR_KEY', 'anthropic-version': '2023-06-01'}).status_code)"
# Should print: 200

# 4. Run tests
uv run pytest

# 5. Start the bot
uv run python -m proposal_assistant.main
# Should see: ⚡️ Bolt app is running!

# 6. Docker (optional)
docker compose -f docker-compose.dev.yml up -d
docker logs -f proposal-assistant-dev
```