# Proposal Assistant

A Slack bot that analyzes meeting transcripts and generates proposal documents using AI.

## Features

- **Transcript Analysis** — Analyzes meeting transcripts (.md files) to extract deal information
- **Deal Analysis Generation** — Generates structured Deal Analysis documents in Google Docs
- **Proposal Deck Creation** — Creates Proposal Decks in Google Slides from approved analyses
- **Cloud LLM** — Uses Anthropic Claude API (Claude Sonnet 4.5) for AI-powered content generation
- **Web Content** — Fetches and incorporates web content from URLs in messages
- **Auto-Sharing** — Automatically shares documents with Slack channel members

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Slack      │────▶│  Proposal    │────▶│   Google    │
│   User       │◀────│  Assistant   │◀────│   Drive     │
└─────────────┘     └──────────────┘     └─────────────┘
                          │
                          ▼
                    ┌──────────────┐
                    │  LLM Engine  │
                    │ (Anthropic)  │
                    │Claude Sonnet │
                    └──────────────┘
```

## Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                  PROPOSAL ASSISTANT WORKFLOW                         │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐
  │  1. User     │  Upload .md transcript file
  │  uploads     │  with message "Analyse"
  │  file        │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  2. Bot      │  • Extracts client name from transcript
  │  analyzes    │  • Creates folder structure in Shared Drive
  │  transcript  │  • Builds context for LLM
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  3. LLM      │  • Generates Deal Analysis content
  │  generates   │  • Identifies missing information
  │  analysis    │  • Extracts key deal details
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  4. Bot      │  • Creates Google Doc in Shared Drive
  │  creates     │  • Populates with Deal Analysis
  │  Doc         │  • Shares with channel members
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  5. User     │  • Reviews Deal Analysis document
  │  reviews     │  • Clicks [Approve] or [Reject]
  │  & approves  │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  6. LLM      │  • Generates 12-slide proposal content
  │  generates   │  • Uses Deal Analysis as input
  │  proposal    │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  7. Bot      │  • Duplicates Slides template
  │  creates     │  • Populates slides with content
  │  Deck        │  • Shares with channel members
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  8. Done!    │  User receives link to
  │              │  completed Proposal Deck
  └──────────────┘
```

## Quick Start

### 1. Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Slack workspace with admin access
- Google Cloud project with Drive, Docs, and Slides APIs enabled
- Anthropic API key (from [console.anthropic.com](https://console.anthropic.com))

### 2. Installation

```bash
# Clone and install dependencies
git clone <repo-url>
cd proposal-assistant-v1
uv sync
```

### 3. Google Cloud Setup

#### 3.1 Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable APIs:
   - Google Drive API
   - Google Docs API
   - Google Slides API
4. Create a Service Account:
   - Go to IAM & Admin → Service Accounts
   - Create service account (e.g., `proposal-bot`)
   - Create JSON key and download it
   - Save the key securely (never commit to repo)

#### 3.2 Create Shared Drive (Required)

> **Important:** Service accounts have no personal Drive storage. You must use a Shared Drive.

1. In Google Drive, create a new Shared Drive (e.g., "Proposal Assistant")
2. Add the service account email as a **Content Manager**:\
   `proposal-bot-v1@your-project.iam.gserviceaccount.com`
3. Create a root folder in the Shared Drive for proposals
4. Copy the folder ID from the URL (the part after `/folders/`)

#### 3.3 Upload Proposal Template

1. Upload your PowerPoint template (.pptx) to the Shared Drive
2. Right-click → Open with → Google Slides (converts it)
3. Copy the presentation ID from the URL

### 4. Claude API Setup

Set your Anthropic API key in the `.env` file (see next section). No local model installation required.

### 5. Configuration

```bash
# Copy example environment file
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Slack Configuration
SLACK_BOT_TOKEN="xoxb-..."
SLACK_APP_TOKEN="xapp-..."
SLACK_SIGNING_SECRET="..."

# Google Configuration
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'   # Full JSON content
GOOGLE_DRIVE_ROOT_FOLDER_ID="1abc..."                          # Shared Drive folder ID
PROPOSAL_TEMPLATE_SLIDE_ID="1xyz..."                           # Google Slides template ID

# LLM Configuration
ANTHROPIC_API_KEY="sk-ant-..."

# Optional — App Settings
LOG_LEVEL="INFO"
ENVIRONMENT="development"
```

### 6. Slack App Setup

1. Create a new Slack app at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** under Settings → Socket Mode
3. Add **Bot Token Scopes** under OAuth & Permissions:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `commands`
   - `files:read`
   - `groups:history`
   - `groups:read`
   - `im:history`
   - `im:read`
   - `users:read`
   - `users:read.email`
4. Add Slash Command: `/pa-status`
5. Enable **Event Subscriptions** and subscribe to:
   - `message.channels`
   - `message.groups`
   - `message.im`
6. Enable **Interactivity & Shortcuts** (for approval buttons)
7. Generate an **App-Level Token** with `connections:write` scope
8. Install the app to your workspace

### 7. Run the Bot

```bash
uv run python -m proposal_assistant.main
```

You should see:

```
⚡️ Bolt app is running!
```

## Usage

### Basic Analysis

1. Create or join a Slack channel
2. Invite the bot: `/invite @ProposalAssistant`
3. Upload a transcript with the message `Analyse`

### Example Transcript Format

```markdown
# Discovery Call - Acme Corp
Date: 2024-01-15
Attendees: John Smith (Acme), Jane Doe (Renessai)

## Discussion

John: Thanks for taking the time to meet with us.
We're looking to modernize our data infrastructure.

Jane: Can you tell me more about the challenges you're facing?

John: Our main issues are:
1. Slow query performance - reports take hours to generate
2. Data silos - marketing and sales don't talk to each other
3. Scaling concerns - we're growing 30% year over year

Jane: What's your timeline for this project?

John: We'd like to have something in place by Q3.
Budget-wise, we're looking at around $500K for the initial implementation.

## Next Steps
- Schedule technical deep-dive
- Prepare initial proposal
```

### With Web Content

Include URLs for additional context:

```
Analyse https://acme-corp.com/about
```

(Attach the .md file to this message)

### Check Bot Status

```
/pa-status
```

## Commands Reference

| Command | Description |
| --- | --- |
| `Analyse` | Analyze attached .md transcript file(s) |
| `Yes` / `No` | Approve or reject proposal deck creation (or use buttons) |
| `Regenerate` | Create a new version of the Deal Analysis |
| `/pa-status` | Check bot status, Claude API health, and metrics |

## Folder Structure Created

For each client, the bot creates:

```
📁 Shared Drive Root
  └── 📁 {client_name}/
      ├── 📁 Meetings/        # Original transcripts
      ├── 📁 Analyse here/    # Deal Analysis documents
      ├── 📁 Proposals/       # Generated proposal decks
      └── 📁 References/      # Reference materials
```

## Development

### Setup

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/proposal_assistant --cov-report=html

# Run linter
uv run ruff check src/

# Format code
uv run black src/

# Type checking
uv run pyright src/
```

### Docker (Local Development)

```bash
# Start bot with docker-compose
docker compose -f docker-compose.dev.yml up -d

# View logs
docker logs -f proposal-assistant-dev
```

For production deployment, CI/CD, monitoring, and operations, see ops-and-deployment.md.

### Utility Scripts

```bash
# Check service account Drive quota
uv run python scripts/check_quota.py

# Check folder permissions
uv run python scripts/check_folder.py

# Inspect Slides template structure
uv run python scripts/inspect_template.py

# Upload and convert PPTX template
uv run python scripts/upload_template.py
```

## Troubleshooting

### Bot not responding

1. Check `/pa-status` to verify the bot is running
2. Ensure the bot is invited to the channel
3. Check that the Anthropic API key is set correctly in `.env`
4. Check Docker logs: `docker logs proposal-assistant`

### "Claude API" errors

1. Verify your `ANTHROPIC_API_KEY` is set correctly in `.env`
2. Check API key validity: visit [console.anthropic.com](https://console.anthropic.com)
3. Ensure outbound HTTPS connectivity to `api.anthropic.com`

### Google Drive "File not found" errors

1. Ensure you're using a **Shared Drive** folder (not personal Drive)
2. Verify the service account has **Content Manager** access
3. Check that the folder/template IDs are correct

### "Storage quota exceeded" error

1. Service accounts have 0 GB personal storage — you **must** use a Shared Drive
2. Check the Shared Drive has available space

### "Placeholder not found" warnings

1. The Slides template structure doesn't match expected placeholders
2. This is normal for PPTX-converted templates
3. Content will still be added to available placeholders

### State data missing for approval

1. Ensure the bot wasn't restarted between analysis and approval
2. State is persisted in `data/threads/` directory
3. If state is lost, start over with `Analyse`

## Environment Variables

| Variable | Description | Required | Default |
| --- | --- | --- | --- |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token (xoxb-...) | Yes | — |
| `SLACK_APP_TOKEN` | Slack app-level token (xapp-...) | Yes | — |
| `SLACK_SIGNING_SECRET` | Slack signing secret for request verification | Yes | — |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON content of service account key | Yes | — |
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Shared Drive folder ID for proposals | Yes | — |
| `PROPOSAL_TEMPLATE_SLIDE_ID` | Google Slides template ID | Yes | — |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude LLM | Yes | — |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No | `INFO` |
| `ENVIRONMENT` | Runtime environment (development, staging, production) | No | `development` |

## Project Documentation

| Document | Purpose |
| --- | --- |
| [**README.md**](http://README.md) (this file) | Quick start, setup, and usage reference |
| project-context.md | Product context, workflows, templates, LLM integration details |
| prd.md | Formal requirements, API contracts, data models, acceptance criteria |
| technical-design.md | Architecture, implementation plan, task breakdown, testing strategy |
| ops-and-deployment.md | CI/CD, Docker, monitoring, runbooks, scaling, incident response |
| PROJECT_PLAN.md | Generic project lifecycle template (Phase 0–15) |

## License

Proprietary — Renessai