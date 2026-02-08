# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Proposal Assistant is a Slack bot for Renessai that analyzes meeting transcripts and generates proposal documents. Users upload `.md` transcript files in Slack, the bot produces a Deal Analysis (Google Doc), and upon approval generates a Proposal Deck (Google Slides from a template).

## Commands

```bash
# Install dependencies (uses uv package manager)
uv sync                    # all deps
uv sync --no-dev           # production only

# Run the bot
uv run python -m proposal_assistant.main

# Tests
uv run pytest                                          # all tests
uv run pytest tests/unit/test_state_machine.py         # single file
uv run pytest tests/unit/test_state_machine.py::test_name  # single test
uv run pytest --cov=src/proposal_assistant --cov-report=html

# Lint & format
uv run ruff check src/
uv run black src/
uv run pyright src/

# Docker
docker build -t proposal-assistant .
docker run --env-file .env proposal-assistant
```

## Architecture

### Two-Step Workflow (State Machine)

The bot follows a state machine pattern defined in `state/machine.py` with explicit `TRANSITIONS` dict mapping `(State, Event) -> State`:

```
IDLE → GENERATING_DEAL_ANALYSIS → WAITING_FOR_APPROVAL → GENERATING_DECK → DONE
                                                              ↕
                                         ERROR ←──────────────┘
```

1. User sends "Analyse" with `.md` file attachments → bot generates a **Deal Analysis** Google Doc via LLM
2. User reviews and clicks approve (or uploads revised doc) → bot generates a **Proposal Deck** by populating a Google Slides template

Thread state (`ThreadState` dataclass in `state/models.py`) persists as JSON files in `data/threads/`.

### Module Boundaries

- **`slack/`** — Slack Bolt event handlers and Block Kit message builders. Entry point for all user interactions. `handlers.py` orchestrates the workflow by calling into other modules.
- **`llm/`** — LLM interaction via OpenAI-compatible SDK (pointed at Ollama). `client.py` handles retries, chunking large transcripts (>32K tokens), and cloud fallback (OpenAI/Anthropic). Prompt templates live in `llm/prompts/`.
- **`drive/`** — Google Drive API: folder creation (`folders.py`), file permissions (`permissions.py`), and API wrapper (`client.py`).
- **`docs/`** — Google Docs API: creates Deal Analysis documents from LLM-structured JSON (`deal_analysis.py`).
- **`slides/`** — Google Slides API: copies a template deck and populates placeholders with LLM-generated content (`proposal_deck.py`).
- **`state/`** — State machine (`machine.py`), state/event enums and `ThreadState` model (`models.py`), JSON persistence (`storage.py`).
- **`web/`** — URL content fetcher for supplementary web research.
- **`config.py`** — Singleton `Config` dataclass loaded from env vars via `@lru_cache`.

### LLM Integration

- Primary: Ollama (local, `qwen2.5:14b`) via OpenAI SDK pointed at `/v1` endpoint
- Fallback: OpenAI or Anthropic cloud APIs (requires user consent via Slack buttons)
- LLM returns structured JSON; `_extract_json()` handles markdown code fences
- Large transcripts are auto-chunked and summarized before analysis
- 12-slide proposal deck structure: `slide_1_cover` through `slide_12_next_steps`

### Google Drive Folder Structure

The bot auto-creates per-client folders: `{ClientName}/{Meetings, Analyse here, Proposals, References}`

## Configuration

All config via environment variables (`.env` file). Required vars:
- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`
- `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `PROPOSAL_TEMPLATE_SLIDE_ID`

Optional: `OLLAMA_NUM_CTX` (default 32768), `CLOUD_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOG_LEVEL`, `ENVIRONMENT`

## Code Style

- Python 3.12+, line length 88 (black + ruff)
- Type checking: pyright in standard mode
- Build system: hatchling (wheel packages `src/proposal_assistant`)
