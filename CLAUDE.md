# CLAUDE.md — Proposal Assistant

Instructions for Claude Code working in this repo.

---

## Commands

```bash
# Install (uv preferred; pip3 fallback if uv unavailable)
uv sync                            # all deps
uv sync --no-dev                   # prod only
pip3 install -e ".[dev]"           # fallback

# Run
uv run python -m proposal_assistant.main

# Tests
uv run pytest                                          # all
uv run pytest tests/unit/ -v                           # unit only
uv run pytest tests/integration/ -v                    # integration only
uv run pytest tests/unit/test_llm_client.py -v         # single file
uv run pytest tests/unit/test_llm_client.py::TestGenerateDealAnalysis -v  # single class
uv run pytest --cov=src/proposal_assistant --cov-report=html              # coverage

# Lint / format / type-check
uv run ruff check src/
uv run black src/
uv run pyright src/

# Docker
docker compose -f docker-compose.dev.yml up -d
```

---

## Architecture

**Slack bot** using `slack-bolt` (Socket Mode) + **Anthropic Python SDK** (`anthropic` package, direct `messages.create`) + **Google APIs** (Drive, Docs, Slides via service account).

- **LLM SDK:** `anthropic >= 0.40.0` (NOT `claude-agent-sdk` — that package is not installed)
- **Model:** `claude-sonnet-4-5-20250929` (Claude Sonnet 4.5)
- **Supported file types:** `.md`, `.txt`, `.docx`
- **State persistence:** JSON files in `data/threads/`
- **Package manager:** `uv` (use `pip3` fallback if uv unavailable)

### Request Flow

```
main.py (event routing)
  -> slack/handlers.py (orchestration)
       -> llm/agent.py (LLM calls via anthropic SDK)
       -> drive/ (folder creation, file ops)
       -> docs/ (Deal Analysis document)
       -> slides/ (Proposal Deck from template)
       -> drive/permissions.py (sharing)
       -> state/machine.py (transition tracking)
```

### State Machine

```
IDLE -> GENERATING_DEAL_ANALYSIS (ANALYSE_REQUESTED)
IDLE -> WAITING_FOR_INPUTS (INPUTS_MISSING)
IDLE -> GENERATING_DECK (PROPOSE_REQUESTED)

GENERATING_DEAL_ANALYSIS -> WAITING_FOR_APPROVAL (DEAL_ANALYSIS_CREATED)
GENERATING_DEAL_ANALYSIS -> ERROR (FAILED)

WAITING_FOR_APPROVAL -> GENERATING_DECK (APPROVED)
WAITING_FOR_APPROVAL -> DONE (REJECTED)
WAITING_FOR_APPROVAL -> GENERATING_DECK (UPDATED_DEAL_ANALYSIS_PROVIDED)
WAITING_FOR_APPROVAL -> GENERATING_DEAL_ANALYSIS (REGENERATE_REQUESTED)

GENERATING_DECK -> DONE (DECK_CREATED)
GENERATING_DECK -> ERROR (FAILED)

ERROR -> GENERATING_DEAL_ANALYSIS (ANALYSE_REQUESTED)
ERROR -> GENERATING_DEAL_ANALYSIS (CLOUD_CONSENT_GIVEN)
ERROR -> DONE (REJECTED)
```

Two workflows: **Analyse** (transcript -> deal analysis -> approval -> deck) and **Propose** (uploaded deal analysis -> deck directly, skipping analysis).

### Source Tree

```
src/proposal_assistant/
  main.py               # Entry point, Bolt app, event routing
  config.py             # Config dataclass, get_config() singleton
  constants.py          # SUPPORTED_TRANSCRIPT_EXTENSIONS
  health.py             # Claude API / Drive / storage health checks
  status.py             # BotStatus singleton (uptime, request count)
  slack/
    handlers.py         # All message/action handlers
    messages.py         # Block Kit formatters, ERROR_MESSAGES map
  llm/
    agent.py            # Anthropic client wrapper (generate_deal_analysis, generate_proposal_content)
    context_builder.py  # Token counting, chunking, context assembly
    prompts/            # System + user prompts for deal analysis & proposal deck
    tools.py            # Dead code (imports non-existent claude_agent_sdk)
    mcp_server.py       # Dead code (imports non-existent claude_agent_sdk)
    hooks.py            # Dead code (imports non-existent claude_agent_sdk)
  drive/
    client.py           # Google Drive API wrapper
    folders.py          # Client folder creation
    permissions.py      # File sharing with channel members
  docs/
    client.py           # Google Docs API wrapper
    deal_analysis.py    # Deal Analysis document population
  slides/
    client.py           # Google Slides API wrapper
    proposal_deck.py    # Proposal Deck population
  state/
    machine.py          # State transitions (TRANSITIONS dict)
    models.py           # State, Event enums, ThreadState dataclass
    storage.py          # JSON file persistence
  utils/
    parsing.py          # Client name extraction
    validation.py       # Transcript validation
    doc_parser.py       # Deal analysis document parser (for Propose flow)
    document_parser.py  # .docx binary parser
    logging.py          # Structured JSON logger
  web/
    fetcher.py          # URL content fetching
```

---

## LLM Integration

Entry point: `llm/agent.py` using `anthropic.Anthropic()` (cached singleton via `_get_client()`).

Key functions:
- `generate_deal_analysis(transcript, references, web_content)` -> dict with `content`, `missing_info`, `raw_response`
- `generate_proposal_content(deal_analysis)` -> dict with `content`, `raw_response`
- `_query_with_retry(prompt, system_prompt, temperature)` -> str (with configurable retry + exponential backoff)
- `_prepare_transcript(transcript)` -> str (merges multiple transcripts, chunk-summarizes if over threshold)
- `_extract_json(text)` -> dict (handles markdown code fences)

All config flows through `config.py:get_config()`. LLM params: model, max_tokens, temperature, retries, backoff, chunk_threshold, chunk_size.

---

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack app-level token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | Slack signing secret |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON content of service account key |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Shared Drive folder ID |
| `ANTHROPIC_API_KEY` | Anthropic API key (`sk-ant-...`) |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5-20250929` | Model ID |
| `ANTHROPIC_MAX_TOKENS` | `8192` | Max response tokens |
| `ANTHROPIC_TEMPERATURE` | `0.3` | Sampling temperature |
| `ANTHROPIC_MAX_RETRIES` | `3` | Retry count for LLM calls |
| `ANTHROPIC_RETRY_BACKOFF` | `1,2,4` | Comma-separated backoff seconds |
| `ANTHROPIC_CHUNK_THRESHOLD` | `32000` | Token count before chunk-summarizing |
| `ANTHROPIC_CHUNK_SIZE` | `8000` | Tokens per chunk |
| `PROPOSAL_TEMPLATE_SLIDE_ID` | `""` | Google Slides template ID (optional) |
| `PROPOSAL_TEMPLATE_PATH` | `template/Renessai basic template 10_2025.pptx` | Local PPTX template path |
| `BOT_ENABLED` | `true` | Feature flag |
| `SLACK_ALERT_CHANNEL` | `""` | Alert channel |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ENVIRONMENT` | `development` | Environment name |

Health check constants exported from `health.py`: `ANTHROPIC_MODELS_URL`, `ANTHROPIC_VERSION_HEADER`, `HEALTH_CHECK_TIMEOUT`.

---

## Testing Patterns

### Mock Pattern for Anthropic SDK

```python
from unittest.mock import MagicMock, patch

# Patch the cached client getter
with patch("proposal_assistant.llm.agent._get_client") as mock_get:
    mock_client = MagicMock()
    mock_get.return_value = mock_client

    # Build a mock response
    response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = '{"deal_analysis": {...}, "missing_info": []}'
    response.content = [mock_block]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_client.messages.create.return_value = response
```

Anthropic sends `system` as a separate kwarg (not in messages list):
```python
call_kwargs = mock_client.messages.create.call_args
# call_kwargs.kwargs["system"] = "system prompt"
# call_kwargs.kwargs["messages"] = [{"role": "user", "content": "..."}]
```

### Config Cache Clearing

```python
from proposal_assistant.config import get_config
get_config.cache_clear()  # Required before tests that set env vars
```

### Minimal Env Vars for Tests

```python
env = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_APP_TOKEN": "xapp-test",
    "SLACK_SIGNING_SECRET": "test-secret",
    "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type":"service_account"}',
    "GOOGLE_DRIVE_ROOT_FOLDER_ID": "test-folder-id",
    "ANTHROPIC_API_KEY": "sk-ant-test",
}
```

### Test Fixtures

```
tests/fixtures/
  transcripts/           # valid_transcript.md, empty_transcript.md, long_transcript.md, valid_transcript.txt
  llm_responses/         # deal_analysis_response.json, proposal_deck_response.json
```

No `slack_events/` directory exists.

---

## Key Product Rules

1. **Grounded content** — Use only provided inputs. Never invent facts. Flag missing info as "Unknown / Not provided".
2. **Two-step workflow** — Always generate Deal Analysis first (Analyse path). Proposal Deck only after explicit approval. Exception: Propose path skips analysis.
3. **Template integrity** — Never modify the original Slides template. Always duplicate. Keep fonts/colors/branding unchanged.
4. **Drive scoping** — Only write to `/Clients/{ClientName}/` folder structure. Never delete/overwrite existing client docs.
5. **Friendly errors** — Never expose raw API errors. Use the error messages defined in `slack/messages.py:ERROR_MESSAGES`.
6. **No secret logging** — Never log API keys, tokens, or full transcripts. Log only IDs, links, status codes.
7. **Content overflow** — If text exceeds placeholder bounds, split across slides. Do NOT shrink font size.

---

## Pre-existing Test Failures

These failures predate our changes and are not our responsibility:

- `test_drive_client.py::TestDownloadFile::test_calls_get_media_with_file_id`
- `test_slides_client.py::TestDuplicateTemplate::test_sends_correct_copy_request`
- `test_slides_client.py::TestPopulateProposalDeck::test_deletes_existing_text_before_insert`

---

## Reference Docs

| Document | Purpose |
|----------|---------|
| `docs/CLOUD.md` | GCP deployment, git branch workflow |
| `docs/DEPLOY.md` | Deployment instructions |
| `docs/NOTE.md` | Development notes |
| `docs/NEW_BRANCH.md` | Branch management |
| `docs/USER_GUIDE.md` | End-user guide |
