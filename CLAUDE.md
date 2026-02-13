# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (uv preferred; pip3 fallback if uv unavailable)
uv sync                          # or: pip3 install -e ".[dev]"

# Run
uv run python -m proposal_assistant.main

# Tests
uv run pytest                              # all tests
uv run pytest tests/unit/ -v               # unit only
uv run pytest tests/integration/ -v        # integration only
uv run pytest tests/unit/test_health.py -v                        # single file
uv run pytest tests/unit/test_health.py::TestCheckClaudeApi -v    # single class
uv run pytest tests/unit/test_health.py::TestCheckClaudeApi::test_healthy_when_200 -v  # single test
uv run pytest --cov=src/proposal_assistant --cov-report=html      # coverage (CI enforces 80%)

# Lint & format
uv run ruff check src/
uv run black --check src/                  # line-length = 100
uv run pyright src/

# Docker
docker compose -f docker-compose.dev.yml up -d   # dev (hot-reload src/)
docker compose up -d                              # prod
```

## Architecture

Slack bot (slack-bolt, Socket Mode) that transforms meeting transcripts into:
1. **Deal Analysis** — structured Google Doc summarizing client discovery
2. **Proposal Deck** — Google Slides presentation from Renessai template

**Stack:** Python 3.12 · `anthropic` SDK (direct `messages.create`, NOT `claude-agent-sdk`) · Google Drive/Docs/Slides APIs (service account) · JSON file state persistence (`data/threads/`)

### Two-Step Workflow
1. User uploads `.md` transcript + "Analyse" → bot generates Deal Analysis doc → shares in Drive
2. User approves ("Yes") → bot generates Proposal Deck from Deal Analysis → shares deck
- "No" ends workflow. "Regenerate" creates versioned new doc (v2, v3...)
- "Propose" with attached `.docx`/`.md` skips transcript analysis, goes straight to deck

### State Machine
```
IDLE → GENERATING_DEAL_ANALYSIS → WAITING_FOR_APPROVAL → GENERATING_DECK → DONE
  ↓                                       ↓
WAITING_FOR_INPUTS                      DONE (rejected)
Any → ERROR (on failure) → GENERATING_DEAL_ANALYSIS (on retry)
```
States/events: `state/models.py`. Transitions: `state/machine.py`. Persistence: `state/storage.py` → `data/threads/{channel}_{ts}.json`.

### Request Flow
```
slack/handlers.py (orchestrator)
  → llm/agent.py (LLM calls)
  → drive/client.py + drive/folders.py (folder creation)
  → docs/deal_analysis.py or slides/proposal_deck.py (document population)
  → drive/permissions.py (sharing)
  → state/machine.py (state transitions throughout)
```

Handlers are the glue — each handler (`handle_analyse_command`, `handle_approval`, `handle_regenerate`, etc.) orchestrates the full sub-workflow including error handling and Slack messaging.

## LLM Integration

**Entry point:** `src/proposal_assistant/llm/agent.py`

Key functions:
- `generate_deal_analysis(transcript, references, web_content)` → `{"content": dict, "missing_info": list, "raw_response": str}`
- `generate_proposal_content(deal_analysis)` → `{"content": dict (12 slide keys), "raw_response": str}`
- `_query_with_retry(prompt, system_prompt)` — retry with exponential backoff (configurable via config)
- `_prepare_transcript(transcript)` — merges multiple transcripts, auto-chunks if over token threshold

All LLM config (model, max_tokens, temperature, retries, backoff, chunk thresholds) flows through `config.py:get_config()`. No silent fallbacks — missing config fails loudly.

**Dead code:** `llm/tools.py`, `llm/mcp_server.py`, `llm/hooks.py` import `claude_agent_sdk` which is not installed. These files are unused.

## Configuration

All env-based config is centralized in `config.py:get_config()` (cached singleton via `@lru_cache`). No other `src/` modules should read `os.getenv` directly. The `scripts/` directory is the intentional exception — standalone utilities that only need 1-2 vars.

Health check constants (`ANTHROPIC_MODELS_URL`, `ANTHROPIC_VERSION_HEADER`, `HEALTH_CHECK_TIMEOUT`) are exported from `health.py` and reused by `handlers.py` via `check_claude_api()`.

### Required env vars
```
SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SIGNING_SECRET
GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_DRIVE_ROOT_FOLDER_ID
ANTHROPIC_API_KEY
```

### Optional (with defaults from config.py)
```
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_MAX_TOKENS=8192
ANTHROPIC_TEMPERATURE=0.3
ANTHROPIC_MAX_RETRIES=3
ANTHROPIC_RETRY_BACKOFF=1,2,4
ANTHROPIC_CHUNK_THRESHOLD=32000
ANTHROPIC_CHUNK_SIZE=8000
PROPOSAL_TEMPLATE_SLIDE_ID=
PROPOSAL_TEMPLATE_PATH=template/Renessai basic template 10_2025.pptx
LOG_LEVEL=INFO
ENVIRONMENT=development
BOT_ENABLED=true
SLACK_ALERT_CHANNEL=
```

## Testing Patterns

No `conftest.py` — fixtures are defined locally in each test file.

### Mocking the Anthropic client
```python
@pytest.fixture
def mock_client():
    with patch("proposal_assistant.llm.agent._get_client") as mock_get:
        client = MagicMock()
        mock_get.return_value = client
        yield client

# Building a mock response:
response = MagicMock()
block = MagicMock()
block.text = '{"deal_analysis": {...}, "missing_info": []}'
response.content = [block]
mock_client.messages.create.return_value = response
```

### Config cache in tests
`get_config()` is `@lru_cache` — tests must clear it to pick up env var changes:
```python
@pytest.fixture(autouse=True)
def clear_config_cache():
    get_config.cache_clear()
    yield
    get_config.cache_clear()
```

### Minimal required env vars for tests
```python
REQUIRED_ENV_VARS = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_APP_TOKEN": "xapp-test",
    "SLACK_SIGNING_SECRET": "test-secret",
    "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}',
    "GOOGLE_DRIVE_ROOT_FOLDER_ID": "folder-123",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
}
```

### Test fixtures
- `tests/fixtures/transcripts/` — sample `.md` transcripts (valid, empty, long)
- `tests/fixtures/llm_responses/` — JSON responses for deal_analysis, proposal_deck
- `tests/fixtures/slack_events/` — sample Slack message payloads

## Key Product Rules

1. **Grounded content** — only use provided inputs. Never invent facts. Flag missing info as "Unknown / Not provided"
2. **Two-step workflow** — Deal Analysis first, Proposal Deck only after explicit "Yes"
3. **Template integrity** — never modify original Slides template; always duplicate. Arial 14pt, theme colors only (`scheme_color`, not hardcoded hex)
4. **Drive scoping** — only write to `/Clients/{ClientName}/`. Never delete existing client docs
5. **Friendly errors** — never expose raw API errors. Use error messages from `slack/messages.py`
6. **No secret logging** — never log API keys, tokens, or full transcripts
7. **Content overflow** — split across slides rather than shrinking font

## Pre-existing Test Failures

These tests fail due to pre-existing issues (not related to LLM migration):
- `test_drive_client.py::TestDownloadFile::test_calls_get_media_with_file_id`
- `test_slides_client.py::TestDuplicateTemplate::test_sends_correct_copy_request`
- `test_slides_client.py::TestPopulateProposalDeck::test_deletes_existing_text_before_insert`

## Reference Docs

- `docs/prd.md` — requirements, acceptance criteria, error handling matrix
- `docs/project-context.md` — product context, workflows, templates
- `docs/technical-design.md` — architecture, implementation plan

Note: these docs reference the old Ollama/OpenAI stack for LLM sections — this CLAUDE.md is the source of truth for the current LLM integration.
