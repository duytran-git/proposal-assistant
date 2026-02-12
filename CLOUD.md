# Cloud Infrastructure — Proposal Assistant

## How It Runs

The bot runs on a Google Cloud VM without your laptop. Here's what's happening:

```
Your Slack workspace
        ↕ (Socket Mode — outbound connection)
GCE VM: proposal-assistant-prod (europe-north1-b)
  └── Docker container: proposal-assistant
        ├── Listens for Slack messages
        ├── Calls Anthropic API (Claude) to generate content
        ├── Calls Google APIs to create Docs/Slides
        └── Responds back to Slack
```

- **Socket Mode** means the bot connects outward to Slack — no incoming ports needed
- **Docker `restart: unless-stopped`** means it auto-restarts on crash or VM reboot
- **No GPU** — Claude runs in Anthropic's cloud, not on your VM

---

## How to Check It's Running

### Quick status check

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker ps --filter name=proposal-assistant --format 'table {{.Status}}'"
```

Expected output: `Up X hours (healthy)`

### Check recent logs

```bash
# Last 5 minutes
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker logs --since 5m proposal-assistant 2>&1"

# Last 1 hour
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker logs --since 1h proposal-assistant 2>&1"

# Follow logs live
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker logs -f proposal-assistant"
```

Press `Ctrl+C` to stop following logs.

### Check if VM itself is running

```bash
gcloud compute instances describe proposal-assistant-prod \
  --zone=europe-north1-b \
  --format="value(status)"
```

Expected output: `RUNNING`

### From Slack

Just send a message to the bot. If it responds, it's running.

---

## How to Stop It

### Stop the bot (keep VM running)

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose down"
```

### Stop the VM (stops everything, stops billing for compute)

```bash
gcloud compute instances stop proposal-assistant-prod --zone=europe-north1-b
```

What stops billing:
- VM compute (~$100/month) — **stopped immediately**
- Bot goes offline — **no longer responds in Slack**

What still costs money:
- 30 GB SSD disk (~$5/month) — stored even when VM is stopped
- Any Anthropic API usage already made this billing cycle

### Start the VM again

```bash
gcloud compute instances start proposal-assistant-prod --zone=europe-north1-b
```

The bot auto-starts with the VM (Docker `restart: unless-stopped`).

---

## Costs

### Monthly cost breakdown

| Service | What | Estimated Cost | Billed By |
|---------|------|----------------|-----------|
| GCE VM (`e2-standard-4`) | 4 vCPU, 16 GB RAM, runs 24/7 | ~$100/month | Google Cloud |
| Boot disk (30 GB SSD) | VM storage | ~$5/month | Google Cloud |
| Network (outbound HTTPS) | Slack + API traffic | ~$2/month | Google Cloud |
| Anthropic API (Claude) | Per-request LLM calls | ~$50–200/month | Anthropic |
| Google APIs (Drive/Docs/Slides) | Document creation | Free tier | Google Cloud |
| **Total** | | **~$150–310/month** | |

Anthropic cost depends on usage — more proposals generated = higher cost.

### How to check Google Cloud costs

**GCP Console (web):**
1. Go to https://console.cloud.google.com/billing
2. Select project: `renessai-proposal-assistant`
3. Click **Reports** to see daily/monthly spend
4. Click **Budgets & alerts** to set spending limits

**From terminal:**

```bash
# Current month cost estimate
gcloud billing projects describe renessai-proposal-assistant \
  --format="value(billingAccountName)"
```

Or visit directly:
- **Billing overview:** https://console.cloud.google.com/billing
- **Cost breakdown:** https://console.cloud.google.com/billing/reports
- **VM costs:** https://console.cloud.google.com/compute/instances

### How to check Anthropic API costs

1. Go to https://console.anthropic.com
2. Log in with your Anthropic account
3. Click **Usage** in the sidebar
4. See daily/monthly token usage and cost

### Cost-saving tips

| Action | Saves |
|--------|-------|
| Stop VM when not in use (`gcloud compute instances stop ...`) | ~$100/month compute |
| Use `claude-haiku-4-5-20251001` instead of Sonnet (set `ANTHROPIC_MODEL` in `.env`) | ~50–70% on API costs |
| Set a budget alert in GCP console | Prevents surprise bills |

---

## Where Everything Lives

| What | Where |
|------|-------|
| Source code | GitHub: `duytran-git/proposal-assistant` |
| VM | GCP: `proposal-assistant-prod` in `europe-north1-b` |
| Bot container | Docker on VM: `proposal-assistant` |
| App data (thread state) | VM: `/opt/proposal-assistant/data/` |
| Logs | VM: `/opt/proposal-assistant/logs/` |
| Environment config | VM: `/opt/proposal-assistant/.env` |
| Generated documents | Google Drive: `/Clients/{ClientName}/` |
| Anthropic API dashboard | https://console.anthropic.com |
| GCP billing dashboard | https://console.cloud.google.com/billing |
| Slack app settings | https://api.slack.com/apps |
