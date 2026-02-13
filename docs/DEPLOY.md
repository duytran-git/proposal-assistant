# Deployment Guide — Proposal Assistant

## Prerequisites

- Docker and Docker Compose installed locally
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- `.env` file configured (copy from `.env.example` and fill in values)
- Git remote set up (`origin` → GitHub)

| Field | Value |
|-------|-------|
| VM name | `proposal-assistant-prod` |
| Zone | `europe-north1-b` |
| Repo path on VM | `/opt/proposal-assistant` |
| Branch | `production-deploy-prep` |

---

## Phase 1 — Validate Code (after every change)

### Step 1: Format

```bash
python3 -m black src/ tests/
```

### Step 2: Lint

```bash
python3 -m ruff check src/
```

If issues found, auto-fix with `python3 -m ruff check src/ --fix`, then re-run.

### Step 3: Test

```bash
python3 -m pytest
```

All tests must pass (except the 3 pre-existing failures — see Troubleshooting).

### One-liner for Steps 1–3

```bash
python3 -m black src/ tests/ && python3 -m ruff check src/ && python3 -m pytest
```

If this passes, move to Phase 2. If not, fix and repeat.

---

## Phase 2 — Test Locally in Docker

### Step 4: Build the image

```bash
docker compose build
```

### Step 5: Start the container

```bash
docker compose up -d
```

### Step 6: Verify it's healthy

```bash
docker ps --filter name=proposal-assistant
```

Expected: `Up ... (healthy)`. If it shows `Restarting`, check logs:

```bash
docker logs proposal-assistant 2>&1 | tail -20
```

### Step 7: Smoke test

Send a test message in Slack to confirm the bot responds.

### Step 8: Stop the local container

```bash
docker compose down
```

Stop local before deploying to VM — both connect to the same Slack app and will cause duplicate responses.

---

## Phase 3 — Commit and Push

### Step 9: Stage your changes

```bash
git add <changed files>
```

Never `git add .env` — it contains secrets.

### Step 10: Commit

```bash
git commit -m "your commit message"
```

### Step 11: Push

```bash
git push origin production-deploy-prep
```

---

## Phase 4 — Deploy to GCE VM

### Step 12: Pull latest code on VM

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && git pull origin production-deploy-prep"
```

### Step 13: Build on VM

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose build"
```

### Step 14: Restart on VM

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose down && docker compose up -d"
```

### Step 15: Verify on VM

```bash
sleep 10
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker ps --filter name=proposal-assistant --format '{{.Status}}'"
```

Expected: `Up ... (healthy)`.

### Step 16: Check logs on VM

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker logs --since 60s proposal-assistant 2>&1"
```

No errors = deploy complete.

### One-liner for Steps 12–14

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && git pull origin production-deploy-prep && docker compose down && docker compose build && docker compose up -d"
```

---

## Updating .env Only (no code changes)

No rebuild needed — just copy and restart.

### Local

```bash
docker compose restart
```

### VM

```bash
# Copy .env to VM
gcloud compute scp .env proposal-assistant-prod:/opt/proposal-assistant/.env --zone=europe-north1-b

# Restart
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose restart"
```

---

## First-Time VM Setup (one-off)

Only needed when setting up a new VM or after a VM rebuild.

### 1. Clone the repo

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b

# On the VM:
sudo git clone https://github.com/duytran-git/proposal-assistant.git /opt/proposal-assistant
cd /opt/proposal-assistant
git checkout production-deploy-prep
```

### 2. Copy .env to VM

```bash
# From your LOCAL machine:
gcloud compute scp .env proposal-assistant-prod:/opt/proposal-assistant/.env --zone=europe-north1-b
```

### 3. Fix volume permissions

```bash
# On the VM:
cd /opt/proposal-assistant
sudo chmod 777 logs/ data/
touch logs/proposal_assistant.log
sudo chmod 666 logs/proposal_assistant.log
```

### 4. Build and start

```bash
docker compose build
docker compose up -d
```

---

## Troubleshooting

### Container keeps restarting

```bash
docker logs proposal-assistant 2>&1 | tail -20
```

| Cause | Fix |
|-------|-----|
| `PermissionError` on logs/ | `sudo chmod 777 logs/` |
| Missing env var | Check `.env` has all required vars (see `.env.example`) |
| Bad API key | Verify `ANTHROPIC_API_KEY` is valid |

### Health check failing

```bash
docker exec proposal-assistant .venv/bin/python -c \
  "from proposal_assistant.health import check; print(check())"
```

### Duplicate bot responses in Slack

Both local and VM connect to the same Slack app. Only run one at a time.

```bash
# Stop local
docker compose down

# Stop VM
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose down"
```

### Pre-existing test failures (ignore these)

These 3 tests fail before our changes and are not our responsibility:
- `test_drive_client.py::test_calls_get_media_with_file_id`
- `test_slides_client.py::test_sends_correct_copy_request`
- `test_slides_client.py::test_deletes_existing_text_before_insert`
