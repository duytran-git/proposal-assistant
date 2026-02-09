# Production Architecture & GCP Setup Guide: Proposal Assistant

**Version:** 1.0\
**Last Updated:** 2026-02-09\
**Author:** Duy Tran\
**Status:** Draft

---

## 1. Architecture Overview

### 1.1 Production Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Google Cloud Platform                                    │
│                     Project: renessai-proposal-assistant                     │
│                     Region: europe-north1 (Finland)                          │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              GCE VM: proposal-assistant-prod                          │  │
│  │              Machine type: g2-standard-8 (8 vCPU, 32 GB RAM)         │  │
│  │              GPU: NVIDIA L4 (24 GB VRAM)                             │  │
│  │              Boot disk: 50 GB SSD (Ubuntu 22.04 LTS)                 │  │
│  │              Zone: europe-north1-b                                    │  │
│  │                                                                       │  │
│  │   ┌─────────────────────┐       ┌──────────────────────────────┐     │  │
│  │   │  proposal-assistant │       │  ollama                      │     │  │
│  │   │  (Docker container) │──────▶│  (Docker container + GPU)    │     │  │
│  │   │                     │       │                              │     │  │
│  │   │  • Python 3.12      │       │  • qwen2.5:14b model loaded  │     │  │
│  │   │  • Slack Bolt       │       │  • NVIDIA L4 passthrough     │     │  │
│  │   │  • Socket Mode      │       │  • Port 11434 (internal)     │     │  │
│  │   │  • Non-root user    │       │  • num_ctx=32768             │     │  │
│  │   └────────┬────────────┘       └──────────────────────────────┘     │  │
│  │            │                                                          │  │
│  │   ┌────────▼──────────────────────────────────────────────────┐      │  │
│  │   │                 Persistent Disk (SSD)                      │      │  │
│  │   │                                                            │      │  │
│  │   │  /opt/proposal-assistant/                                  │      │  │
│  │   │  ├── data/threads/        # State JSON files               │      │  │
│  │   │  ├── data/documents/      # Document metadata              │      │  │
│  │   │  ├── logs/                # Structured JSON logs           │      │  │
│  │   │  └── backups/             # Daily state backups            │      │  │
│  │   └────────────────────────────────────────────────────────────┘      │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐   │
│  │  Google Drive     │  │  Google Docs     │  │  Google Slides         │   │
│  │  (Shared Drive)   │  │  API v1          │  │  API v1                │   │
│  │                   │  │                  │  │                        │   │
│  │  /Clients/        │  │  Deal Analysis   │  │  Proposal Decks        │   │
│  │  /Templates/      │  │  creation        │  │  from template         │   │
│  │  /Marketing/      │  │                  │  │                        │   │
│  └──────────────────┘  └──────────────────┘  └────────────────────────┘   │
│                                                                             │
│  ┌──────────────────┐                                                      │
│  │  IAM / Service    │  proposal-bot@renessai-proposal-assistant.iam       │
│  │  Account          │  Scoped to: Drive, Docs, Slides APIs only           │
│  └──────────────────┘                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │                              │
          │ Socket Mode (outbound)       │ HTTPS (outbound)
          │ wss://wss-primary.slack.com  │
          ▼                              ▼
┌───────────────────────┐     ┌───────────────────────────────┐
│    Slack API           │     │  Cloud LLM Fallback (optional) │
│                        │     │                                │
│  • Socket Mode events  │     │  • OpenAI API (gpt-4o)        │
│  • Web API responses   │     │  • Anthropic API (claude)     │
│  • Interactive actions  │     │  • Only with user consent     │
│  • File downloads      │     │  • No data sent without ask   │
└───────────────────────┘     └───────────────────────────────┘
```

### 1.2 Network Architecture

```
┌─────────────────────────────────────────────────┐
│           GCE VM Firewall Rules                  │
│                                                  │
│  INBOUND:                                        │
│  ├── SSH (port 22) — restricted to admin IPs     │
│  └── ICMP — for health monitoring                │
│                                                  │
│  OUTBOUND (all allowed):                         │
│  ├── Slack API (wss://, https://)                │
│  ├── Google APIs (https://googleapis.com)        │
│  ├── Ollama (internal, port 11434)               │
│  └── Cloud LLM APIs (https://, if fallback)      │
│                                                  │
│  INTERNAL (Docker bridge network):               │
│  └── proposal-assistant ↔ ollama (port 11434)    │
│                                                  │
│  NO inbound HTTP/HTTPS needed                    │
│  (Socket Mode = outbound-only WebSocket)         │
└─────────────────────────────────────────────────┘
```

### 1.3 Why This Architecture

| Decision | Rationale |
| --- | --- |
| **Single VM** | 5 concurrent users does not justify multi-node. Simpler to operate, debug, and maintain. |
| **GCE over GKE** | Kubernetes is overkill for one bot + one LLM. GCE gives full control at lower complexity. |
| **GCE over Cloud Run** | Cloud Run is stateless and time-limited. Ollama needs persistent GPU memory; bot needs long-running Socket Mode. |
| **europe-north1 (Finland)** | Closest GCP region to Renessai team (EET timezone). Low latency to Google APIs. |
| **g2-standard-8** | G2 machine series supports L4 GPU. 8 vCPU + 32 GB RAM handles Ollama + bot simultaneously. |
| **NVIDIA L4 GPU** | Best price/performance for inference. 24 GB VRAM fits qwen2.5:14b with room for 32K context. LLM response: \~5–10s vs \~45s on CPU. |
| **Docker Compose** | Two-container setup (bot + ollama) is simple to manage. No orchestrator needed. |
| **Socket Mode** | No inbound ports needed. No load balancer, no SSL certificate, no domain name required. |
| **Persistent Disk** | State data and logs survive VM restarts. Backed up daily. |

---

## 2. GCP Project Setup

### 2.1 Create GCP Project

```bash
# Create the project
gcloud projects create renessai-proposal-assistant \
    --name="Proposal Assistant" \
    --organization=YOUR_ORG_ID

# Set as active project
gcloud config set project renessai-proposal-assistant

# Enable billing (required for Compute Engine and GPUs)
gcloud billing projects link renessai-proposal-assistant \
    --billing-account=YOUR_BILLING_ACCOUNT_ID
```

### 2.2 Enable Required APIs

```bash
# Compute Engine (for the VM)
gcloud services enable compute.googleapis.com

# Google Drive API
gcloud services enable drive.googleapis.com

# Google Docs API
gcloud services enable docs.googleapis.com

# Google Slides API
gcloud services enable slides.googleapis.com

# IAM (for service accounts)
gcloud services enable iam.googleapis.com

# Cloud Logging (optional, for centralized logs)
gcloud services enable logging.googleapis.com
```

### 2.3 Create Service Account for the Bot

```bash
# Create service account
gcloud iam service-accounts create proposal-bot \
    --display-name="Proposal Assistant Bot" \
    --description="Service account for Proposal Assistant Slack bot"

# Note the email:
# proposal-bot@renessai-proposal-assistant.iam.gserviceaccount.com

# Create and download JSON key
gcloud iam service-accounts keys create keys/proposal-bot-key.json \
    --iam-account=proposal-bot@renessai-proposal-assistant.iam.gserviceaccount.com

# IMPORTANT: Never commit this key to git
echo "keys/" >> .gitignore
```

### 2.4 Request GPU Quota

GPU quota is not available by default. You must request it.

```bash
# Check current GPU quota for europe-north1
gcloud compute regions describe europe-north1 \
    --format="table(quotas.filter(metric='NVIDIA_L4_GPUS'))"

# If quota is 0, request increase:
# 1. Go to: https://console.cloud.google.com/iam-admin/quotas
# 2. Filter: "NVIDIA L4" + Region "europe-north1"
# 3. Request increase to 1
# 4. Typical approval time: 1-3 business days
```

---

## 3. VM Provisioning

### 3.1 Create the VM

```bash
# Create VM with L4 GPU
gcloud compute instances create proposal-assistant-prod \
    --project=renessai-proposal-assistant \
    --zone=europe-north1-b \
    --machine-type=g2-standard-8 \
    --accelerator=type=nvidia-l4,count=1 \
    --maintenance-policy=TERMINATE \
    --restart-on-failure \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-ssd \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --metadata=startup-script='#!/bin/bash
        echo "VM started at $(date)" >> /var/log/startup.log' \
    --tags=proposal-assistant \
    --scopes=default

# Reserve a static internal IP (optional, for stable internal DNS)
gcloud compute addresses create proposal-assistant-ip \
    --region=europe-north1 \
    --subnet=default
```

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

# Block all other inbound (default deny is already in place)
# No HTTP/HTTPS inbound needed — Socket Mode is outbound only
```

### 3.3 SSH into the VM

```bash
gcloud compute ssh proposal-assistant-prod \
    --zone=europe-north1-b \
    --project=renessai-proposal-assistant
```

---

## 4. VM Environment Setup

Run these commands on the VM after SSH.

### 4.1 Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Verify
docker --version
docker compose version
```

### 4.2 Install NVIDIA Container Toolkit

```bash
# Add NVIDIA repository
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install toolkit
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify GPU is accessible from Docker
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 4.3 Clone Repository and Configure

```bash
# Create application directory
sudo mkdir -p /opt/proposal-assistant
sudo chown $USER:$USER /opt/proposal-assistant
cd /opt/proposal-assistant

# Clone repository
git clone <your-repo-url> .

# Create data directories
mkdir -p data/threads data/documents logs backups

# Copy environment file
cp .env.example .env
```

### 4.4 Configure Environment Variables

```bash
nano /opt/proposal-assistant/.env
```

```bash
# =============================================================
# PRODUCTION ENVIRONMENT — Proposal Assistant
# =============================================================

# --- Slack ---
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# --- Google (Service Account) ---
# Option A: Inline JSON (recommended for Docker)
GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"renessai-proposal-assistant",...}'

# Option B: File path (if mounted)
# GOOGLE_SERVICE_ACCOUNT_FILE=/app/keys/proposal-bot-key.json

# --- Google Drive ---
GOOGLE_DRIVE_ROOT_FOLDER_ID=1ABCxyz_your_shared_drive_folder_id

# --- Google Slides Template ---
PROPOSAL_TEMPLATE_SLIDE_ID=1XYZabc_your_template_presentation_id

# --- LLM (Ollama — internal Docker network) ---
OLLAMA_BASE_URL=http://ollama:11434/v1
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_NUM_CTX=32768

# --- Cloud LLM Fallback (optional) ---
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# --- App Settings ---
ENVIRONMENT=production
LOG_LEVEL=INFO

# --- Alerting ---
SLACK_ALERT_CHANNEL=#proposal-assistant-alerts

# --- Feature Flags ---
BOT_ENABLED=true
```

---

## 5. Docker Compose — Production

### 5.1 Production Compose File

```yaml
# docker-compose.yml (production)
version: "3.9"

services:
  proposal-assistant:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: proposal-assistant
    restart: unless-stopped
    env_file: .env
    environment:
      - ENVIRONMENT=production
      - OLLAMA_BASE_URL=http://ollama:11434/v1
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    depends_on:
      ollama:
        condition: service_healthy
    networks:
      - internal
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
    # No ports needed — Socket Mode is outbound only

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    volumes:
      - ollama-models:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    networks:
      - internal
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  ollama-models:
    driver: local

networks:
  internal:
    driver: bridge
```

### 5.2 First-Time Deployment

```bash
cd /opt/proposal-assistant

# Build and start containers
docker compose up -d

# Pull the LLM model (first time only — takes ~5 minutes)
docker exec ollama ollama pull qwen2.5:14b

# Verify model is loaded
docker exec ollama ollama list
# Should show: qwen2.5:14b    8.0 GB

# Verify GPU is being used
docker exec ollama nvidia-smi
# Should show qwen2.5 process using GPU memory

# Check bot is running
docker compose ps
# Both containers should show "Up" and "healthy"

# Check bot logs
docker logs -f proposal-assistant
# Should show: ⚡️ Bolt app is running!

# Test health check
docker exec proposal-assistant python -c "from proposal_assistant.health import check; print(check())"
```

### 5.3 Verify End-to-End

1. Open Slack, go to a channel where the bot is invited
2. Type `/pa-status` — bot should respond with all-green health checks
3. Upload a test transcript (.md file) with message `Analyse`
4. Verify Deal Analysis doc appears in correct Drive folder
5. Click "Yes" to approve deck creation
6. Verify Proposal Deck appears in Drive

---

## 6. Automated Operations

### 6.1 Systemd Service (Auto-Start on Boot)

```bash
sudo nano /etc/systemd/system/proposal-assistant.service
```

```ini
[Unit]
Description=Proposal Assistant Slack Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=your-username
WorkingDirectory=/opt/proposal-assistant
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
```

```bash
# Enable auto-start
sudo systemctl enable proposal-assistant
sudo systemctl start proposal-assistant

# Check status
sudo systemctl status proposal-assistant
```

### 6.2 Daily Backup Cron Job

```bash
# Create backup script
cat > /opt/proposal-assistant/scripts/backup-state.sh << 'EOF'
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

echo "$(date): Backup complete — $BACKUP_DIR/state-$DATE.tar.gz" >> /var/log/proposal-assistant-backup.log
EOF

chmod +x /opt/proposal-assistant/scripts/backup-state.sh

# Schedule daily at 2 AM EET
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/proposal-assistant/scripts/backup-state.sh") | crontab -
```

### 6.3 State Cleanup Cron Job

```bash
# Create cleanup script
cat > /opt/proposal-assistant/scripts/cleanup-state.sh << 'EOF'
#!/bin/bash
DATA_DIR="/opt/proposal-assistant/data/threads"

# Remove DONE threads older than 90 days
DONE_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; -delete

# Remove ERROR threads older than 30 days
ERROR_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; -delete

echo "$(date): Cleaned $DONE_COUNT done + $ERROR_COUNT error threads" >> /var/log/proposal-assistant-cleanup.log
EOF

chmod +x /opt/proposal-assistant/scripts/cleanup-state.sh

# Schedule monthly on the 1st at 3 AM
(crontab -l 2>/dev/null; echo "0 3 1 * * /opt/proposal-assistant/scripts/cleanup-state.sh") | crontab -
```

### 6.4 Log Rotation

```bash
sudo nano /etc/logrotate.d/proposal-assistant
```

```
/opt/proposal-assistant/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 your-username your-username
}
```

---

## 7. CI/CD — GitHub Actions to GCE

### 7.1 GitHub Secrets Required

Set these in GitHub repository Settings → Secrets and variables → Actions:

| Secret | Value | Source |
| --- | --- | --- |
| `PROD_HOST` | External IP of the GCE VM | `gcloud compute instances describe proposal-assistant-prod --format='get(networkInterfaces[0].accessConfigs[0].natIP)'` |
| `PROD_USER` | SSH username on the VM | Your GCE username |
| `PROD_SSH_KEY` | Private SSH key | `cat ~/.ssh/id_ed25519` (or generate a deploy key) |
| `SLACK_DEPLOY_CHANNEL` | Channel ID for deploy notifications | e.g., `C0123456789` |
| `SLACK_DEPLOY_BOT_TOKEN` | Bot token for deploy notifications | Same as SLACK_BOT_TOKEN or a separate bot |

### 7.2 Generate Deploy SSH Key

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/proposal-assistant-deploy

# Add public key to the VM
gcloud compute instances add-metadata proposal-assistant-prod \
    --zone=europe-north1-b \
    --metadata-from-file=ssh-keys=<(echo "deploy-user:$(cat ~/.ssh/proposal-assistant-deploy.pub)")

# Copy private key content to GitHub secret PROD_SSH_KEY
cat ~/.ssh/proposal-assistant-deploy
```

### 7.3 Deploy Workflow

The deploy workflow from `ops-and-deployment.md` applies directly. On merge to `main`:

1. GitHub Actions builds and tests the code
2. SSHs into the GCE VM
3. Pulls latest code
4. Rebuilds Docker images
5. Restarts containers
6. Runs smoke test (health check + Ollama verification)
7. Notifies Slack channel with deploy status

---

## 8. Monitoring Setup

### 8.1 Uptime Monitoring

```bash
# Simple self-monitoring via cron (checks every 5 minutes)
cat > /opt/proposal-assistant/scripts/health-monitor.sh << 'EOF'
#!/bin/bash

# Check bot container
BOT_STATUS=$(docker inspect --format='{{.State.Health.Status}}' proposal-assistant 2>/dev/null)
if [ "$BOT_STATUS" != "healthy" ]; then
    # Send alert via curl to Slack webhook
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🔴 CRITICAL: proposal-assistant container is '"$BOT_STATUS"'"}' \
        "$SLACK_WEBHOOK_URL"
fi

# Check Ollama
OLLAMA_OK=$(curl -sf http://localhost:11434/ | grep -c "Ollama")
if [ "$OLLAMA_OK" -eq 0 ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🔴 CRITICAL: Ollama is not responding"}' \
        "$SLACK_WEBHOOK_URL"
fi

# Check disk usage
DISK_USAGE=$(df /opt/proposal-assistant --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_USAGE" -gt 80 ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🟡 WARNING: Disk usage at '"$DISK_USAGE"'%"}' \
        "$SLACK_WEBHOOK_URL"
fi
EOF

chmod +x /opt/proposal-assistant/scripts/health-monitor.sh

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL /opt/proposal-assistant/scripts/health-monitor.sh") | crontab -
```

### 8.2 GCP Native Monitoring (Optional)

```bash
# Install Google Cloud Ops Agent for system metrics
curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
sudo bash add-google-cloud-ops-agent-repo.sh --also-install

# This automatically reports to GCP Monitoring:
# - CPU usage
# - Memory usage
# - Disk I/O
# - Network traffic
# - GPU utilization (with NVIDIA driver)

# Create uptime check in GCP Console:
# Monitoring → Uptime checks → Create
# Protocol: TCP, Port: 22 (SSH as heartbeat)
# Check frequency: 5 minutes
# Alert: Email + Slack webhook
```

---

## 9. Cost Estimate

### 9.1 Monthly Cost Breakdown

| Component | Specification | Monthly Cost (USD) | Notes |
| --- | --- | --- | --- |
| **GCE VM** | g2-standard-8 (8 vCPU, 32 GB RAM) | \~$250 | On-demand; \~$175 with 1-year committed use |
| **NVIDIA L4 GPU** | 1x L4 (24 GB VRAM) | \~$150 | On-demand; \~$105 with 1-year committed use |
| **Boot disk** | 50 GB SSD (pd-ssd) | \~$8.50 |  |
| **Network egress** | Minimal (Socket Mode outbound, API calls) | \~$1–5 | Very low traffic volume |
| **Google APIs** | Drive, Docs, Slides | $0 | Free tier covers \~10–20 requests/day easily |
| **Static IP** (optional) | 1 external IP | $0 (while attached) | Free when attached to running VM |
|  |  |  |  |
| **Total (on-demand)** |  | **\~$410–415/month** |  |
| **Total (1-year committed)** |  | **\~$290–295/month** | \~30% savings |
| **Total (3-year committed)** |  | **\~$205–210/month** | \~50% savings |

### 9.2 Cost Optimization Options

| Strategy | Savings | Trade-off |
| --- | --- | --- |
| **1-year committed use discount** | \~30% | Must commit to 1 year |
| **3-year committed use discount** | \~50% | Must commit to 3 years |
| **Drop GPU (CPU-only inference)** | \-$150/month | LLM response: \~45s instead of \~5–10s |
| **Downgrade to g2-standard-4** | \-$60/month | 4 vCPU, 16 GB RAM — tighter but works |
| **Schedule VM shutdown (nights/weekends)** | \~40% of VM cost | Bot offline outside business hours |
| **Use preemptible/spot VM** | \~60–70% | VM can be terminated with 30s notice — not recommended for production |

### 9.3 VM Scheduling (Optional Cost Saver)

If the bot is only needed during business hours (Mon–Fri, 8AM–8PM EET):

```bash
# Create instance schedule
gcloud compute resource-policies create instance-schedule business-hours \
    --region=europe-north1 \
    --vm-start-schedule="0 8 * * 1-5" \
    --vm-stop-schedule="0 20 * * 1-5" \
    --timezone="Europe/Helsinki"

# Attach to VM
gcloud compute instances add-resource-policies proposal-assistant-prod \
    --resource-policies=business-hours \
    --zone=europe-north1-b

# Saves ~40% of compute cost (12h/day * 5 days = 60h/week vs 168h/week)
```

---

## 10. Disaster Recovery

### 10.1 VM Failure

| Scenario | Recovery |
| --- | --- |
| VM hangs/unresponsive | `gcloud compute instances reset proposal-assistant-prod --zone=europe-north1-b` |
| VM deleted accidentally | Re-create from snapshot (see below) |
| Disk corruption | Restore from daily backup |
| Region outage | Re-deploy in `europe-west1` (Belgium) — requires DNS/config change |

### 10.2 Snapshot Schedule

```bash
# Create snapshot schedule for the boot disk
gcloud compute resource-policies create snapshot-schedule daily-snapshots \
    --region=europe-north1 \
    --max-retention-days=14 \
    --daily-schedule \
    --start-time=04:00 \
    --storage-location=eu

# Attach to the VM's disk
gcloud compute disks add-resource-policies proposal-assistant-prod \
    --resource-policies=daily-snapshots \
    --zone=europe-north1-b
```

### 10.3 Restore from Snapshot

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
    --machine-type=g2-standard-8 \
    --accelerator=type=nvidia-l4,count=1 \
    --disk=name=proposal-assistant-restored,boot=yes
```

---

## 11. Security Hardening

### 11.1 VM-Level Security

```bash
# Disable password auth (SSH key only)
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades

# Restrict Docker socket access
sudo chmod 660 /var/run/docker.sock

# Set up fail2ban for SSH brute-force protection
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

### 11.2 Service Account Least Privilege

The service account should have **only** these permissions:

```bash
# No IAM roles needed at project level
# All access is via Google Drive sharing (Content Manager on Shared Drive)

# Verify: service account should have NO project-level roles
gcloud projects get-iam-policy renessai-proposal-assistant \
    --flatten="bindings[].members" \
    --filter="bindings.members:proposal-bot@"
# Should return empty
```

### 11.3 Secrets Management

```bash
# Secure the .env file
chmod 600 /opt/proposal-assistant/.env
chown $USER:$USER /opt/proposal-assistant/.env

# Secure the service account key (if using file-based)
chmod 600 /opt/proposal-assistant/keys/proposal-bot-key.json

# Verify no secrets in git
git log --all --diff-filter=A -- '*.env' 'keys/' '.env*'
# Should return nothing (files were never committed)
```

---

## 12. Maintenance Runbook

### 12.1 Regular Maintenance Schedule

| Task | Frequency | Command |
| --- | --- | --- |
| Check VM health | Daily (automated) | `scripts/health-monitor.sh` |
| Review error logs | Daily during beta, weekly at GA | `docker logs proposal-assistant --since 24h | grep ERROR` |
| Backup state | Daily (automated) | `scripts/backup-state.sh` |
| Clean old state | Monthly (automated) | `scripts/cleanup-state.sh` |
| Update OS packages | Monthly | `sudo apt update && sudo apt upgrade -y` |
| Update Docker images | Monthly | `docker compose pull && docker compose up -d` |
| Update Ollama model | On new release | `docker exec ollama ollama pull qwen2.5:14b` |
| Rotate service account key | Quarterly | See [ops-and-deployment.md](http://ops-and-deployment.md) §6.2 |
| Review GCP billing | Monthly | GCP Console → Billing |
| Test disaster recovery | Quarterly | Restore from snapshot to test VM |

### 12.2 Common Operations

```bash
# --- View logs ---
docker logs -f proposal-assistant                    # Bot logs (live)
docker logs -f ollama                                # Ollama logs (live)
docker logs proposal-assistant --since 1h            # Last hour
docker logs proposal-assistant --since 1h | grep ERROR  # Errors only

# --- Restart services ---
docker compose restart proposal-assistant            # Restart bot only
docker compose restart ollama                        # Restart Ollama only
docker compose restart                               # Restart everything

# --- Deploy update ---
cd /opt/proposal-assistant
git pull origin main
docker compose down
docker compose build --no-cache
docker compose up -d

# --- Check resource usage ---
docker stats                                         # Live resource usage
nvidia-smi                                           # GPU usage
df -h                                                # Disk usage
free -h                                              # Memory usage

# --- Emergency: disable bot ---
# Edit .env, set BOT_ENABLED=false
docker compose restart proposal-assistant

# --- Emergency: full stop ---
docker compose down
```

---

## 13. Document Cross-Reference

| Document | Relationship to This Guide |
| --- | --- |
| `ops-and-deployment.md` | General ops guide — this file provides the GCP-specific implementation |
| `technical-design.md` | Source for architecture decisions and module structure |
| `project-context.md` | Source for product requirements and LLM configuration |
| `prd.md` | Source for performance targets and non-functional requirements |
| `README.md` | Developer setup — this guide covers production setup |
| `CODING_INSTRUCTIONS.md` | Coding standards that apply to all infrastructure code |
