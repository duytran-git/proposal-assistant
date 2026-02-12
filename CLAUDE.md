# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync                          # all (dev + prod)
uv sync --no-dev                 # prod only

# Run the bot
uv run python -m proposal_assistant.main

# Tests
uv run pytest                                    # all tests
uv run pytest tests/unit/ -v                     # unit tests only
uv run pytest tests/integration/ -v              # integration tests only
uv run pytest tests/unit/test_llm_client.py -v   # single file
uv run pytest tests/unit/test_llm_client.py::TestExtractJson -v  # single class
uv run pytest tests/unit/test_llm_client.py::TestExtractJson::test_parses_fenced_json -v  # single test
uv run pytest --cov=src/proposal_assistant --cov-report=html     # coverage

# Lint & format
uv run ruff check src/
uv run black --check src/        # check only
uv run black src/                # fix
uv run pyright src/              # type check

# Docker
docker compose up -d                              # production
docker compose -f docker-compose.dev.yml up -d    # dev (hot-reload)
```

**Note:** `uv` may not be available on all systems. Fall back to `pip3 install -e ".[dev]"` and run commands without the `uv run` prefix.

## Architecture

Slack bot that transforms meeting transcripts into Deal Analysis (Google Doc) and Proposal Deck (Google Slides) through a two-step workflow with an approval gate.

### LLM Integration

Uses `claude_agent_sdk.query()` for one-shot async completions with Claude Sonnet 4.5 (`claude-sonnet-4-5-20250514`). The SDK is used for its `query()` async generator — MCP tools/hooks files exist (`llm/tools.py`, `llm/mcp_server.py`, `llm/hooks.py`) but are not actively wired into the main workflow.

Key module: `src/proposal_assistant/llm/agent.py`
- `generate_deal_analysis(transcript, references, web_content)` → dict with `content`, `missing_info`, `raw_response`
- `generate_proposal_content(deal_analysis)` → dict with `content` (12 slide keys), `raw_response`
- `_query_with_retry()` — 3 retries with 1s/2s/4s exponential backoff; does NOT retry `LLMError`
- `_extract_json()` — parses JSON from LLM responses, handles markdown code fences
- `_prepare_transcript()` — chunk-summarizes transcripts over 32k tokens

### State Machine

`src/proposal_assistant/state/machine.py` — Manages thread lifecycle:
```
IDLE → GENERATING_DEAL_ANALYSIS → WAITING_FOR_APPROVAL → GENERATING_DECK → DONE
```
Transitions are a dict of `(State, Event) → State`. JSON file persistence in `data/threads/`.

### Workflow Orchestration

`src/proposal_assistant/slack/handlers.py` is the main orchestrator. It handles Slack events and coordinates: transcript validation → Drive folder creation → LLM generation → Google Docs/Slides creation → sharing → Slack responses.

### Google APIs

Service account auth. Three parallel wrappers:
- `drive/` — folder creation, file operations
- `docs/` — Deal Analysis document creation (6-section structure)
- `slides/` — template duplication and 12-slide population (`slide_1_cover` through `slide_12_next_steps`)

## Testing Patterns

### Mocking the LLM

```python
def _mock_query_response(text: str):
    async def mock_query(**kwargs):
        msg = MagicMock()
        msg.result = text
        yield msg
    return mock_query

with patch("proposal_assistant.llm.agent.query", side_effect=mock_query):
    result = await generate_deal_analysis("transcript")
```

### Config Fixtures

Tests that touch `get_config()` need a Config fixture with all required fields mocked. The `get_config` LRU cache must be cleared between tests.

## Code Style

- **Black**: line length 100, Python 3.12 target
- **Ruff**: line length 100, Python 3.12 target
- **Pyright**: standard mode (not strict)
- **pytest**: `asyncio_mode = "auto"` — async tests work without `@pytest.mark.asyncio`

## Key Rules

- Never use `openai` package or reference Ollama/`OLLAMA_*` env vars — the project migrated to Anthropic SDK
- Never modify the original Slides template — always duplicate
- Never invent facts in generated content — use "Unknown / Not provided"
- Deal Analysis must be generated and approved before Proposal Deck
- Never expose raw API errors to users — use the error handling matrix in `slack/messages.py`
- `check_ollama_health()` and `use_cloud` param are kept as no-ops for handler compatibility

## Environment Variables

Required: `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_DRIVE_ROOT_FOLDER_ID`, `PROPOSAL_TEMPLATE_SLIDE_ID`, `ANTHROPIC_API_KEY`

Optional: `ANTHROPIC_MODEL` (default: `claude-sonnet-4-5-20250514`), `LOG_LEVEL` (default: `INFO`), `ENVIRONMENT` (default: `development`)

## Pre-existing Test Failures

These test failures predate the LLM migration and are not caused by recent changes:
- `test_drive_client.py::TestDownloadFile::test_calls_get_media_with_file_id`
- `test_slides_client.py::TestDuplicateTemplate::test_sends_correct_copy_request`
- `test_slides_client.py::TestPopulateProposalDeck::test_deletes_existing_text_before_insert`
