# Switching to a New Branch on the Production VM

When you push a new branch and need the VM to run it instead of the old branch.

---

## Step 1: Stop the container on the VM

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && docker compose down"
```

## Step 2: Stop the VM

```bash
gcloud compute instances stop proposal-assistant-prod --zone=europe-north1-b
```

## Step 3: Push the new branch from your local machine

```bash
git push -u origin <new-branch-name>
```

## Step 4: Start the VM

```bash
gcloud compute instances start proposal-assistant-prod --zone=europe-north1-b
```

Wait ~30 seconds for SSH to become available.

## Step 5: Clean up conflicting files, switch branch, build, and start

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && rm -f data/threads/*.json && git fetch origin && git checkout <new-branch-name> && git pull origin <new-branch-name> && docker compose build && docker compose up -d"
```

**Why `rm -f data/threads/*.json`?** — Thread state files are created at runtime and may conflict with files tracked in the new branch. Removing them allows `git checkout` to succeed.

## Step 6: Verify

```bash
sleep 15
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker ps --filter name=proposal-assistant --format '{{.Status}}'"
```

Expected: `Up ... (healthy)`

If unhealthy, check logs:

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker logs --since 60s proposal-assistant 2>&1"
```

---

## One-liner (Steps 5-6 combined)

Replace `<new-branch-name>` with your branch:

```bash
gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="cd /opt/proposal-assistant && rm -f data/threads/*.json && git fetch origin && git checkout <new-branch-name> && git pull origin <new-branch-name> && docker compose build && docker compose up -d" \
&& sleep 15 \
&& gcloud compute ssh proposal-assistant-prod --zone=europe-north1-b \
  --command="docker ps --filter name=proposal-assistant --format '{{.Status}}'"
```
