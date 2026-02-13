# Proposal Assistant

Slack bot that turns meeting transcripts into Deal Analysis docs and Proposal Decks.

## Description

Proposal Assistant is a Slack bot for Renessai consultants and salespeople. Users upload `.md` meeting transcripts and the bot generates a structured Deal Analysis (Google Doc) summarizing client discovery findings. After an approval gate, it creates a Proposal Deck (Google Slides) from Renessai's standard template. Powered by Anthropic's Claude API — no local model or GPU required.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (or pip3 as fallback)
- Slack app configured for Socket Mode with bot and app-level tokens
- Google Cloud service account with Drive, Docs, and Slides APIs enabled
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
- Google Drive root folder ID for client document storage

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url>
cd proposal-assistant
uv sync              # or: pip3 install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials (see Environment Variables below)

# 3. Start the bot
uv run python -m proposal_assistant.main
# Expected: "Starting Proposal Assistant bot in Socket Mode..."
```

## Environment Variables

Create a `.env` file in the project root with these required variables:

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Slack bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack app-level token for Socket Mode (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account credentials JSON string |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Root folder ID in Google Drive for client documents |
| `ANTHROPIC_API_KEY` | Anthropic API key (`sk-ant-...`) |

See [CLAUDE.md](CLAUDE.md) for optional LLM tuning parameters and app settings.

## How It Works

1. User uploads a `.md` transcript in Slack and types **"Analyse"**
2. Bot creates a client folder in Google Drive under `/Clients/{ClientName}/`
3. Bot sends the transcript to Claude and generates a Deal Analysis
4. Bot creates a Google Doc with the analysis, shares it, and posts a link with approval buttons
5. User clicks **"Yes"** to approve — bot generates Proposal Deck content via Claude
6. Bot duplicates the Slides template, populates it with proposal content, and shares the deck
7. Bot posts the deck link — workflow complete

**Alternative paths:** "No" ends the workflow gracefully. "Regenerate" creates a new versioned Deal Analysis (v2, v3...) while keeping the original.

## Docker

Single container deployment — no GPU or sidecar services needed.

```bash
# Production
docker compose up -d --build

# Development (with hot-reload source mount)
docker compose -f docker-compose.dev.yml up -d

# View logs
docker logs -f proposal-assistant
```

The container includes a built-in health check that verifies Claude API connectivity, Google Drive access, and state storage.

## Testing

```bash
uv run pytest                              # All tests
uv run pytest tests/unit/ -v               # Unit tests only
uv run pytest tests/integration/ -v        # Integration tests only
uv run pytest --cov=src/proposal_assistant \
              --cov-report=html            # Coverage report

# Lint and format
uv run ruff check src/
uv run black --check src/                  # Line length: 100
uv run pyright src/
```

## Project Structure

```
src/proposal_assistant/
  main.py          Entry point — initializes Slack Bolt app and registers handlers
  config.py        Environment variable loading, Config dataclass
  health.py        Health checks (Claude API, Google Drive, state storage)
  slack/           Slack event handlers, slash commands, Block Kit message formatters
  llm/             Claude API client, prompt templates, context builder
  drive/           Google Drive API — folder creation, file permissions
  docs/            Google Docs API — Deal Analysis document generation
  slides/          Google Slides API — template duplication and proposal deck population
  state/           State machine (models, transitions, JSON file persistence)
  web/             URL content fetcher for supplementary research
  utils/           Logging, parsing, validation, and alerting utilities
```

## Documentation

- [CLAUDE.md](CLAUDE.md) — Architecture details, LLM integration, environment variables, product rules, and testing patterns
- [docs/prd.md](docs/prd.md) — Product requirements and acceptance criteria
- [docs/technical-design.md](docs/technical-design.md) — Architecture and implementation plan
