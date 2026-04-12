# Production Deployment Guide — Proposal Assistant

**Version:** 2.0\
**Last Updated:** 2026-02-10\
**Author:** Duy Tran\
**Architecture:** Claude Agent SDK (single container, no GPU)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Google Cloud Platform                               │
│                     Project: renessai-proposal-assistant                │
│                     Region: europe-north1 (Finland)                     │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              GCE VM: proposal-assistant-prod                      │  │
│  │              Machine type: e2-standard-4 (4 vCPU, 16 GB RAM)     │  │
│  │              Boot disk: 30 GB SSD (Ubuntu 22.04 LTS)             │  │
│  │              Zone: europe-north1-b                                │  │
│  │              GPU: NONE                                            │  │
│  │                                                                   │  │
│  │   ┌─────────────────────────────────────────────────────────┐     │  │
│  │   │  proposal-assistant (single Docker container)           │     │  │
│  │   │                                                         │     │  │
│  │   │  • Python 3.12 + Node.js 18+                           │     │  │
│  │   │  • Slack Bolt (Socket Mode — outbound only)            │     │  │
│  │   │  • Claude Agent SDK → Anthropic API (cloud)            │     │  │
│  │   │  • Google Drive/Docs/Slides via Service Account        │     │  │
│  │   │  • Non-root user (botuser)                             │     │  │
│  │   └────────┬────────────────────────────────────────────────┘     │  │
│  │            │                                                      │  │
│  │   ┌────────▼────────────────────────────────────────────────┐     │  │
│  │   │              Persistent Storage (bind mounts)           │     │  │
│  │   │  /opt/proposal-assistant/                               │     │  │
│  │   │  ├── data/threads/        # State JSON files            │     │  │
│  │   │  ├── data/documents/      # Document metadata           │     │  │
│  │   │  ├── logs/                # Structured JSON logs        │     │  │
│  │   │  └── backups/             # Daily state backups         │     │  │
│  │   └─────────────────────────────────────────────────────────┘     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│         OUTBOUND ONLY (no inbound HTTP/HTTPS needed)                    │
│         ├── Slack API (wss://, https://)                                │
│         ├── Anthropic API (https://api.anthropic.com)                   │
│         └── Google APIs (https://googleapis.com)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### What Changed from Ollama Architecture

| Before (Ollama) | After (Claude SDK) |
| --- | --- |
| g2-standard-8 (8 vCPU, 32 GB RAM) | **e2-standard-4 (4 vCPU, 16 GB RAM)** |
| NVIDIA L4 GPU (24 GB VRAM) | **No GPU** |
| 50 GB SSD | **30 GB SSD** |
| Two containers (bot + ollama) | **Single container (bot only)** |
| \~$410/month | **\~$150-310/month** |
| GPU quota request (1-3 day wait) | **No quota request needed** |
| NVIDIA Container Toolkit required | **Not needed** |
| Model download (\~8 GB, 5 min) | **No model download** |
| Internal Docker networking (bot→ollama) | **Direct HTTPS to Anthropic API** |

---

## 2. Prerequisites

Before you begin, ensure you have:

- [ ] GCP project created (`renessai-proposal-assistant`)

- [ ] Billing enabled on the GCP project

- [ ] Google APIs enabled: Drive, Docs, Slides, Compute Engine, IAM

- [ ] Service account created with JSON key downloaded

- [ ] Shared Drive set up with service account as Content Manager

- [ ] Proposal Slides template uploaded and converted to Google Slides

- [ ] Slack app created with Socket Mode, all required scopes and events

- [ ] Anthropic API key from [console.anthropic.com](http://console.anthropic.com)

- [ ] SSH key pair for deployment (or `gcloud` CLI configured)

- [ ] All values ready for `.env` file (see §5)

---

## 3. Create GCE VM

### 3.1 Provision the VM

```bash
gcloud compute instances create proposal-assistant-prod \
    --project=renessai-proposal-assistant \
    --zone=europe-north1-b \
    --machine-type=e2-standard-4 \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-ssd \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=proposal-assistant \
    --restart-on-failure \
    --scopes=default
```

No `--accelerator`, no `--maintenance-policy=TERMINATE`, no GPU quota needed.

### 3.2 Firewall Rules

```bash
# Allow SSH from admin IPs only
gcloud compute firewall-rules create allow-ssh-admin \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:22 \
    --source-ranges=YOUR_OFFICE_IP/32 \
    --target-tags=proposal-assistant
```

No inbound HTTP/HTTPS needed — Socket Mode is outbound-only WebSocket.

### 3.3 SSH into the VM

```bash
gcloud compute ssh proposal-assistant-prod \
    --zone=europe-north1-b \
    --project=renessai-proposal-assistant
```

---

## 4. VM Environment Setup

Run all commands below on the VM after SSH.

### 4.1 Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Log out and back in for docker group to take effect
exit
```

SSH back in:

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b

# Verify installation
docker --version
docker compose version
```

**No NVIDIA Container Toolkit needed.** No `nvidia-ctk`, no GPU driver, no CUDA.

### 4.2 Clone Repository

```bash
# Create application directory
sudo mkdir -p /opt/proposal-assistant
sudo chown $USER:$USER /opt/proposal-assistant
cd /opt/proposal-assistant

# Clone repo
git clone <your-repo-url> .

# Create data directories
mkdir -p data/threads data/documents logs backups
```

---

## 5. Configure Environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in all values:

```bash
# =============================================================
# PRODUCTION ENVIRONMENT — Proposal Assistant
# =============================================================

# --- Slack ---
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# --- Google (Service Account) ---
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"renessai-proposal-assistant","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"proposal-bot@renessai-proposal-assistant.iam.gserviceaccount.com",...}'
GOOGLE_DRIVE_ROOT_FOLDER_ID=1ABCxyz_your_shared_drive_folder_id

# --- Google Slides Template ---
PROPOSAL_TEMPLATE_SLIDE_ID=1XYZabc_your_template_presentation_id

# --- LLM — Claude Agent SDK ---
ANTHROPIC_API_KEY=sk-ant-your-api-key

# --- App Settings ---
ENVIRONMENT=production
LOG_LEVEL=INFO
BOT_ENABLED=true

# --- Alerting ---
SLACK_ALERT_CHANNEL=#proposal-assistant-alerts
```

**Removed variables** (do NOT add these):

- ~~OLLAMA_BASE_URL~~
- ~~OLLAMA_MODEL~~
- ~~OLLAMA_NUM_CTX~~
- ~~OPENAI_API_KEY~~

---

## 6. Docker Files

### 6.1 Dockerfile

Verify the repo Dockerfile matches this (per [CLAUDE.md](http://CLAUDE.md) §9):

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

### 6.2 docker-compose.yml (Production)

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
    # No ollama service — Claude Agent SDK uses cloud API

networks:
  internal:
    driver: bridge
```

Single service. No `ollama`. No `depends_on`. No GPU `deploy` section. No named volumes for models.

---

## 7. Build and Deploy

### 7.1 Build Docker Image

```bash
cd /opt/proposal-assistant

# Build
docker compose build

# Verify the build
docker run --rm proposal-assistant:latest node --version
# Should print: v18.x.x

docker run --rm proposal-assistant:latest uv run python -c "import claude_agent_sdk; print('SDK OK')"
# Should print: SDK OK
```

### 7.2 Start the Bot

```bash
docker compose up -d

# Wait for startup (health check start-period is 15s)
sleep 30

# Check container status
docker compose ps
# Should show: proposal-assistant   Up (healthy)

# Check health
docker inspect --format='{{.State.Health.Status}}' proposal-assistant
# Should print: healthy
```

### 7.3 Verify Logs

```bash
docker logs proposal-assistant
# Should show: ⚡️ Bolt app is running!

# Check for errors
docker logs proposal-assistant 2>&1 | grep -i error
# Should return nothing
```

### 7.4 Verify Health Checks

```bash
docker exec proposal-assistant python -c \
    "from proposal_assistant.health import check; import json; print(json.dumps(check(), indent=2))"
```

Expected output:

```json
{
  "claude_api": {"status": "healthy", "provider": "anthropic"},
  "google_drive": {"status": "healthy", "root_folder": "1ABC..."},
  "state_storage": {"status": "healthy", "path": "data/threads"},
  "timestamp": 1739198400.0
}
```

### 7.5 Verify No Ollama References

```bash
docker exec proposal-assistant grep -r "ollama" /app/src/ && \
    echo "WARNING: Ollama references found!" || \
    echo "Clean — no Ollama references"
```

---

## 8. Smoke Test in Slack

Run through the full workflow to confirm production is working:

| Step | Action | Expected Result |
| --- | --- | --- |
| 1 | Type `/pa-status` in Slack | All-green health checks (Claude API, Drive, Storage) |
| 2 | Upload a test `.md` transcript with message "Analyse" | Bot acknowledges within 3 seconds |
| 3 | Wait for Deal Analysis | Google Doc link posted in thread (&lt; 60s) |
| 4 | Open the Doc | Content in 6-section template, correct Drive folder |
| 5 | Check sharing | Doc shared with channel members as Editor |
| 6 | Click "Yes" to approve | Bot starts generating proposal deck |
| 7 | Wait for Proposal Deck | Google Slides link posted in thread (&lt; 120s) |
| 8 | Open the Deck | Slides populated, template formatting preserved |
| 9 | Check sharing | Deck shared with channel members |

If any step fails, check `docker logs proposal-assistant` for details.

---

## 9. Auto-Start on Boot

```bash
sudo tee /etc/systemd/system/proposal-assistant.service > /dev/null << 'EOF'
[Unit]
Description=Proposal Assistant Slack Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=YOUR_USERNAME
WorkingDirectory=/opt/proposal-assistant
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable proposal-assistant
sudo systemctl start proposal-assistant

# Verify
sudo systemctl status proposal-assistant
```

Replace `YOUR_USERNAME` with your actual GCE username.

---

## 10. Daily Backup (cron)

```bash
cat > /opt/proposal-assistant/scripts/backup-state.sh << 'SCRIPT'
#!/bin/bash
BACKUP_DIR="/opt/proposal-assistant/backups"
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=90

mkdir -p "$BACKUP_DIR"

# Backup state data
tar -czf "$BACKUP_DIR/state-$DATE.tar.gz" \
    -C /opt/proposal-assistant data/threads data/documents

# Clean old backups
find "$BACKUP_DIR" -name "state-*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "$(date): Backup done — $BACKUP_DIR/state-$DATE.tar.gz" >> /var/log/proposal-assistant-backup.log
SCRIPT

chmod +x /opt/proposal-assistant/scripts/backup-state.sh

# Schedule daily at 2 AM EET
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/proposal-assistant/scripts/backup-state.sh") | crontab -
```

**Note:** Deal Analysis docs and Proposal Decks live in Google Drive — backed up by Google automatically.

---

## 11. Health Monitoring (cron)

```bash
cat > /opt/proposal-assistant/scripts/health-monitor.sh << 'SCRIPT'
#!/bin/bash

# Check bot container health
BOT_STATUS=$(docker inspect --format='{{.State.Health.Status}}' proposal-assistant 2>/dev/null)
if [ "$BOT_STATUS" != "healthy" ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"🔴 CRITICAL: proposal-assistant is $BOT_STATUS on $(hostname)\"}" \
        "$SLACK_WEBHOOK_URL"
fi

# Check disk usage
DISK_USAGE=$(df /opt/proposal-assistant --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_USAGE" -gt 80 ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"🟡 WARNING: Disk usage at ${DISK_USAGE}% on $(hostname)\"}" \
        "$SLACK_WEBHOOK_URL"
fi

# Check memory usage
MEM_USAGE=$(free | awk '/Mem/{printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -gt 90 ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"🟡 WARNING: Memory usage at ${MEM_USAGE}% on $(hostname)\"}" \
        "$SLACK_WEBHOOK_URL"
fi
SCRIPT

chmod +x /opt/proposal-assistant/scripts/health-monitor.sh

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL /opt/proposal-assistant/scripts/health-monitor.sh") | crontab -
```

---

## 12. State Cleanup (cron)

```bash
cat > /opt/proposal-assistant/scripts/cleanup-state.sh << 'SCRIPT'
#!/bin/bash
DATA_DIR="/opt/proposal-assistant/data/threads"

# Remove DONE threads older than 90 days
DONE_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; 2>/dev/null | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; -delete 2>/dev/null

# Remove ERROR threads older than 30 days
ERROR_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; 2>/dev/null | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; -delete 2>/dev/null

echo "$(date): Cleaned $DONE_COUNT done + $ERROR_COUNT error threads" >> /var/log/proposal-assistant-cleanup.log
SCRIPT

chmod +x /opt/proposal-assistant/scripts/cleanup-state.sh

# Schedule monthly on the 1st at 3 AM
(crontab -l 2>/dev/null; echo "0 3 1 * * /opt/proposal-assistant/scripts/cleanup-state.sh") | crontab -
```

---

## 13. Snapshot Schedule (Disaster Recovery)

```bash
# Create snapshot schedule for automatic disk backups
gcloud compute resource-policies create snapshot-schedule daily-snapshots \
    --region=europe-north1 \
    --max-retention-days=14 \
    --daily-schedule \
    --start-time=04:00 \
    --storage-location=eu

# Attach to the VM's boot disk
gcloud compute disks add-resource-policies proposal-assistant-prod \
    --resource-policies=daily-snapshots \
    --zone=europe-north1-b
```

### Restore from Snapshot

```bash
# List available snapshots
gcloud compute snapshots list --filter="sourceDisk:proposal-assistant-prod"

# Create new disk from snapshot
gcloud compute disks create proposal-assistant-restored \
    --source-snapshot=SNAPSHOT_NAME \
    --zone=europe-north1-b

# Create new VM from restored disk
gcloud compute instances create proposal-assistant-prod-v2 \
    --zone=europe-north1-b \
    --machine-type=e2-standard-4 \
    --disk=name=proposal-assistant-restored,boot=yes \
    --tags=proposal-assistant
```

---

## 14. Security Hardening

### 14.1 SSH Lockdown

```bash
# Disable password auth (SSH key only)
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable auto security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades

# Install fail2ban for SSH brute-force protection
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

### 14.2 Docker Hardening

```bash
# Restrict Docker socket access
sudo chmod 660 /var/run/docker.sock
```

Container already runs as non-root `botuser` (defined in Dockerfile).

### 14.3 Secrets Security

```bash
# Verify .env is locked down
ls -la /opt/proposal-assistant/.env
# Should show: -rw------- (600)

# Verify no secrets in git history
cd /opt/proposal-assistant
git log --all --diff-filter=A -- '*.env' 'keys/' '.env*'
# Should return nothing
```

### 14.4 Credential Rotation Schedule

| Credential | Rotation Frequency | Process |
| --- | --- | --- |
| Google Service Account key | Quarterly | Generate new key in GCP → update .env → `docker compose restart` → delete old key |
| Slack Bot Token | On suspected compromise | Regenerate in Slack app settings → update .env → restart |
| Slack App Token | On suspected compromise | Regenerate in Slack app settings → update .env → restart |
| ANTHROPIC_API_KEY | Quarterly | Regenerate at [console.anthropic.com](http://console.anthropic.com) → update .env → restart |

---

## 15. Update Deployment

### 15.1 Standard Deploy (on merge to main)

```bash
cd /opt/proposal-assistant
git pull origin main
docker compose down
docker compose build --no-cache
docker compose up -d

# Wait and verify
sleep 30
docker inspect --format='{{.State.Health.Status}}' proposal-assistant
docker logs --since 1m proposal-assistant
```

### 15.2 Emergency Rollback

```bash
# Option A: Quick disable
cd /opt/proposal-assistant
sed -i 's/BOT_ENABLED=true/BOT_ENABLED=false/' .env
docker compose restart proposal-assistant

# Option B: Full rollback to previous version
docker compose down
git checkout <previous-commit-sha>
docker compose build --no-cache
docker compose up -d

# Option C: Hard stop
docker compose down
```

### 15.3 Post-Deploy Verification

```bash
# 1. Container running and healthy
docker compose ps
docker inspect --format='{{.State.Health.Status}}' proposal-assistant

# 2. Logs clean
docker logs proposal-assistant --since 2m | grep -i error

# 3. Health checks pass
docker exec proposal-assistant python -c \
    "from proposal_assistant.health import check; check(); print('All healthy')"

# 4. Slack smoke test
# Type /pa-status in Slack — should show all green
```

---

## 16. Operational Runbooks

### 16.1 Bot Not Responding

```bash
# 1. Check container
docker compose ps
docker inspect --format='{{.State.Health.Status}}' proposal-assistant

# 2. Check logs
docker logs proposal-assistant --since 10m

# 3. Check Socket Mode connection
docker logs proposal-assistant 2>&1 | grep -i "bolt\|socket\|connect"

# 4. Restart
docker compose restart proposal-assistant

# 5. If still failing, rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 16.2 Claude API Errors

```bash
# 1. Check API status
curl -s https://status.anthropic.com/api/v2/status.json | python3 -m json.tool

# 2. Check API key is valid
docker exec proposal-assistant python -c "
import httpx, os
resp = httpx.get('https://api.anthropic.com/v1/models',
    headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'},
    timeout=10)
print(f'Status: {resp.status_code}')
"

# 3. If rate limited: bot auto-retries (3x with 1s/2s/4s backoff)
#    Check logs for retry patterns:
docker logs proposal-assistant 2>&1 | grep -i "retry\|rate_limit\|429"
```

### 16.3 Google Drive Permission Errors

```bash
# 1. Verify service account access
docker exec proposal-assistant python -c "
from proposal_assistant.health import check_google_drive
import json
print(json.dumps(check_google_drive(), indent=2))
"

# 2. Check folder exists and service account is Content Manager
# Go to Google Drive → Shared Drive → check member list

# 3. If quota error (429): auto-retries handle it
#    Check Google Cloud Console → APIs & Services → Quotas
```

### 16.4 State Data Corruption

```bash
# 1. Check for corrupt JSON files
cd /opt/proposal-assistant
find data/threads/ -name "*.json" -exec python3 -c "
import json, sys
try:
    json.load(open(sys.argv[1]))
except: print(f'CORRUPT: {sys.argv[1]}')" {} \;

# 2. If corrupt, user must restart with "Analyse"
# State cannot be recovered — this is a known MVP limitation

# 3. Check disk space
df -h /opt/proposal-assistant
```

### 16.5 Disk Full

```bash
# 1. Check usage
df -h /opt/proposal-assistant
du -sh /opt/proposal-assistant/data/ /opt/proposal-assistant/logs/ /opt/proposal-assistant/backups/

# 2. Clean old logs
docker system prune -f

# 3. Clean old state (if not running automatically)
/opt/proposal-assistant/scripts/cleanup-state.sh

# 4. Clean old backups
find /opt/proposal-assistant/backups/ -name "*.tar.gz" -mtime +30 -delete
```

---

## 17. Cost Estimate

| Component | Specification | Monthly Cost (USD) |
| --- | --- | --- |
| GCE VM | e2-standard-4 (4 vCPU, 16 GB RAM) | \~$100 |
| Boot disk | 30 GB SSD (pd-ssd) | \~$5 |
| Network egress | Outbound HTTPS only (minimal) | \~$2 |
| Snapshots | 14-day retention | \~$3 |
| Claude API | Pay-per-use (Anthropic) | \~$50-200 |
| Google APIs | Drive, Docs, Slides | $0 (free tier) |
|  |  |  |
| **Total (on-demand)** |  | **\~$160-310/month** |
| **Total (1-year committed)** |  | **\~$120-270/month** |

### Cost Optimization Options

| Strategy | Savings | Trade-off |
| --- | --- | --- |
| 1-year committed use discount | \~30% on VM | Must commit to 1 year |
| Schedule VM shutdown (nights/weekends) | \~40% on VM | Bot offline outside business hours |
| Downgrade to e2-standard-2 | \~$50/month | 2 vCPU, 8 GB RAM — tight but may work for &lt;5 users |

### VM Scheduling (Optional — business hours only)

```bash
gcloud compute resource-policies create instance-schedule business-hours \
    --region=europe-north1 \
    --vm-start-schedule="0 8 * * 1-5" \
    --vm-stop-schedule="0 20 * * 1-5" \
    --timezone="Europe/Helsinki"

gcloud compute instances add-resource-policies proposal-assistant-prod \
    --resource-policies=business-hours \
    --zone=europe-north1-b
```

---

## 18. CI/CD — GitHub Actions Deploy

### 18.1 GitHub Secrets Required

| Secret | Value |
| --- | --- |
| `PROD_HOST` | External IP of GCE VM |
| `PROD_USER` | SSH username on VM |
| `PROD_SSH_KEY` | Private SSH key for deploy |
| `SLACK_DEPLOY_CHANNEL` | Channel ID for deploy notifications |
| `SLACK_DEPLOY_BOT_TOKEN` | Bot token for deploy notifications |

### 18.2 Generate Deploy SSH Key

```bash
# On local machine
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/proposal-assistant-deploy

# Add public key to VM
gcloud compute instances add-metadata proposal-assistant-prod \
    --zone=europe-north1-b \
    --metadata-from-file=ssh-keys=<(echo "deploy-user:$(cat ~/.ssh/proposal-assistant-deploy.pub)")

# Copy private key content to GitHub secret PROD_SSH_KEY
cat ~/.ssh/proposal-assistant-deploy
```

### 18.3 Deploy Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
    paths-ignore:
      - "docs/**"
      - "*.md"

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t proposal-assistant:${{ github.sha }} .

      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/proposal-assistant
            git pull origin main
            docker compose down
            docker compose build --no-cache
            docker compose up -d
            sleep 30
            docker compose ps
            echo "Deploy complete: $(date)"

      - name: Smoke test
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            STATUS=$(docker inspect --format='{{.State.Health.Status}}' proposal-assistant)
            if [ "$STATUS" != "healthy" ]; then
              echo "FAILED: Container status is $STATUS"
              docker logs --since 2m proposal-assistant
              exit 1
            fi
            docker exec proposal-assistant python -c \
                "from proposal_assistant.health import check; check()"
            echo "Smoke test passed"

      - name: Notify Slack
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          channel-id: ${{ secrets.SLACK_DEPLOY_CHANNEL }}
          slack-message: |
            Deploy ${{ job.status }}: proposal-assistant@${{ github.sha }}
            Commit: ${{ github.event.head_commit.message }}
        env:
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_DEPLOY_BOT_TOKEN }}
```

---

## 19. Maintenance Schedule

| Task | Frequency | How |
| --- | --- | --- |
| Check VM health | Every 5 min (automated) | `scripts/health-monitor.sh` via cron |
| Backup state data | Daily at 2 AM (automated) | `scripts/backup-state.sh` via cron |
| Clean old state | Monthly on 1st (automated) | `scripts/cleanup-state.sh` via cron |
| Review error logs | Daily during beta, weekly at GA | `docker logs proposal-assistant --since 24h | grep ERROR` |
| Update OS packages | Monthly | `sudo apt update && sudo apt upgrade -y` |
| Update Docker base image | Monthly | Update `python:3.12-slim` tag → rebuild → test |
| Update Claude Agent SDK | Monthly | `uv lock --upgrade` → test → deploy |
| Rotate credentials | Quarterly | See §14.4 |
| Review GCP billing | Monthly | GCP Console → Billing |
| Test disaster recovery | Quarterly | Restore snapshot to test VM |
| Update Slides template | On Renessai rebrand | Update `PROPOSAL_TEMPLATE_SLIDE_ID` → verify with `inspect_template.py` → deploy |

---

## 20. Deployment Checklist (Quick Reference)

Copy this for each deploy:

```
## Deploy Checklist — Date: ____

### Pre-Deploy
- [ ] All tests passing on main: uv run pytest
- [ ] Lint clean: uv run ruff check src/ && uv run black --check src/
- [ ] No Ollama references: grep -r "ollama" src/ returns nothing
- [ ] Docker builds locally: docker build -t proposal-assistant .
- [ ] .env has all required vars (check §5)

### Deploy
- [ ] SSH into VM: gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b
- [ ] Pull latest: cd /opt/proposal-assistant && git pull origin main
- [ ] Rebuild: docker compose down && docker compose build --no-cache
- [ ] Start: docker compose up -d
- [ ] Wait 30s, check health: docker inspect --format='{{.State.Health.Status}}' proposal-assistant
- [ ] Check logs: docker logs proposal-assistant --since 2m

### Post-Deploy
- [ ] /pa-status in Slack: all green
- [ ] Upload test transcript with "Analyse": Deal Analysis created
- [ ] Approve: Proposal Deck created
- [ ] Both docs in correct Drive folder with correct sharing

### Rollback (if needed)
- [ ] docker compose down && git checkout <prev-sha> && docker compose build --no-cache && docker compose up -d
```