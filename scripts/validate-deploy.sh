#!/bin/bash
# validate-deploy.sh — Dry-run deployment validation
# Validates Docker build, image contents, config loading, and scripts
# using fake/test credentials. No real services are contacted.
#
# Usage: bash scripts/validate-deploy.sh
# Exit code: 0 if all checks pass, 1 otherwise.

set -euo pipefail

IMAGE_NAME="proposal-assistant-validate-test"
COMPOSE_PROJECT="pa-validate"
PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    RESULTS+=("PASS: $1")
    echo "  ✓ PASS: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    RESULTS+=("FAIL: $1")
    echo "  ✗ FAIL: $1"
}

echo "============================================"
echo " Proposal Assistant — Deploy Validation"
echo "============================================"
echo ""

# ── Check 1: Docker build ──────────────────────────────────────────
echo "[1/10] Docker build"
BUILD_LOG=$(mktemp)
if docker build -t "$IMAGE_NAME" . > "$BUILD_LOG" 2>&1; then
    rm -f "$BUILD_LOG"
    pass "Docker image built successfully"
else
    echo "  Build output (last 20 lines):"
    tail -20 "$BUILD_LOG" | sed 's/^/    /'
    rm -f "$BUILD_LOG"
    fail "Docker build failed"
fi

# ── Check 2: Python packages ─────────────────────────────────────
echo "[2/10] Required Python packages"
CHECK3_OK=true
for pkg in claude_agent_sdk slack_bolt googleapiclient; do
    if docker run --rm "$IMAGE_NAME" .venv/bin/python -c "import $pkg" 2>/dev/null; then
        echo "       $pkg — present"
    else
        echo "       $pkg — MISSING"
        CHECK3_OK=false
    fi
done
if $CHECK3_OK; then
    pass "All required Python packages present"
else
    fail "One or more required Python packages missing"
fi

# ── Check 3: No openai package ─────────────────────────────────────
echo "[3/10] No openai package"
if docker run --rm "$IMAGE_NAME" .venv/bin/python -c "import openai" 2>/dev/null; then
    fail "openai package is installed (should not be)"
else
    pass "openai package not installed"
fi

# ── Check 4: No Ollama references in source ───────────────────────
echo "[4/10] No Ollama references in source"
OLLAMA_HITS=$(grep -ri "ollama" src/ --include="*.py" --exclude="*_backup*" -l 2>/dev/null || true)
if [ -z "$OLLAMA_HITS" ]; then
    pass "No Ollama references in src/"
else
    fail "Ollama references found in: $OLLAMA_HITS"
fi

# ── Check 5: docker-compose.yml valid ─────────────────────────────
echo "[5/10] docker-compose.yml valid"
if docker compose -f docker-compose.yml config > /dev/null 2>&1; then
    pass "docker-compose.yml is valid"
else
    fail "docker-compose.yml failed validation"
fi

# ── Check 6: Container starts (expect health check fail) ──────────
echo "[6/10] Container starts with dummy env"
CONTAINER_NAME="${COMPOSE_PROJECT}-validate"
docker rm -f "$CONTAINER_NAME" > /dev/null 2>&1 || true
CONTAINER_ID=$(docker run -d --name "$CONTAINER_NAME" \
    -e SLACK_BOT_TOKEN=xoxb-test-000000000000-000000000000-xxxxxxxxxxxxxxxxxxxxxxxxxxxx \
    -e SLACK_APP_TOKEN=xapp-1-test-000000000000-0000000000000-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
    -e SLACK_SIGNING_SECRET=test_signing_secret_000000000000 \
    -e GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"test"}' \
    -e GOOGLE_DRIVE_ROOT_FOLDER_ID=1TESTxxxxxxxxxxxxxxxxxxxxxxxxx \
    -e PROPOSAL_TEMPLATE_SLIDE_ID=1TESTxxxxxxxxxxxxxxxxxxxxxxxxx \
    -e ANTHROPIC_API_KEY=sk-ant-test-000000000000000000000000000000000000000000 \
    "$IMAGE_NAME" 2>&1)

if [ -n "$CONTAINER_ID" ]; then
    # Wait briefly for container to start
    sleep 5
    STATE=$(docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    if [ "$STATE" = "running" ] || [ "$STATE" = "exited" ]; then
        pass "Container started (state: $STATE, health check fail expected)"
    else
        fail "Container in unexpected state: $STATE"
    fi
    docker rm -f "$CONTAINER_NAME" > /dev/null 2>&1 || true
else
    fail "Container failed to start"
fi

# ── Check 7: Config module loads with dummy env vars ───────────────
echo "[7/10] Config module loads"
CONFIG_RESULT=$(docker run --rm \
    -e SLACK_BOT_TOKEN=xoxb-test \
    -e SLACK_APP_TOKEN=xapp-test \
    -e SLACK_SIGNING_SECRET=test \
    -e GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account"}' \
    -e GOOGLE_DRIVE_ROOT_FOLDER_ID=test \
    -e PROPOSAL_TEMPLATE_SLIDE_ID=test \
    -e ANTHROPIC_API_KEY=sk-ant-test \
    -e PYTHONPATH=/app/src \
    "$IMAGE_NAME" .venv/bin/python -c "
from proposal_assistant.config import get_config
c = get_config()
assert c.anthropic_api_key == 'sk-ant-test'
assert c.slack_bot_token == 'xoxb-test'
print('OK')
" 2>&1)
if [[ "$CONFIG_RESULT" == *"OK"* ]]; then
    pass "get_config() loads correctly"
else
    fail "Config module failed: $CONFIG_RESULT"
fi

# ── Check 8: State machine module loads ────────────────────────────
echo "[8/10] State machine module loads"
STATE_RESULT=$(docker run --rm -e PYTHONPATH=/app/src "$IMAGE_NAME" .venv/bin/python -c "
from proposal_assistant.state.models import State, Event
from proposal_assistant.state.machine import StateMachine
print('OK')
" 2>&1)
if [[ "$STATE_RESULT" == *"OK"* ]]; then
    pass "State machine module loads correctly"
else
    fail "State machine module failed: $STATE_RESULT"
fi

# ── Check 9: Cron scripts syntax check ────────────────────────────
echo "[9/10] Cron scripts syntax check"
CHECK10_OK=true
for script in scripts/backup-state.sh scripts/cleanup-state.sh scripts/health-monitor.sh; do
    if [ -f "$script" ]; then
        if bash -n "$script" 2>/dev/null; then
            echo "       $script — syntax OK"
        else
            echo "       $script — syntax ERROR"
            CHECK10_OK=false
        fi
    else
        echo "       $script — not found (skipped)"
    fi
done
if $CHECK10_OK; then
    pass "All cron scripts pass syntax check"
else
    fail "One or more cron scripts have syntax errors"
fi

# ── Check 10: Cleanup ─────────────────────────────────────────────
echo "[10/10] Cleanup"
docker rm -f "$CONTAINER_NAME" > /dev/null 2>&1 || true
docker rmi "$IMAGE_NAME" > /dev/null 2>&1 || true
pass "Cleanup complete"

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "============================================"
echo " Summary: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "============================================"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "RESULT: FAIL"
    exit 1
else
    echo "RESULT: ALL CHECKS PASSED"
    exit 0
fi
