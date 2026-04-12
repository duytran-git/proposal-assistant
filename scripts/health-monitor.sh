#!/bin/bash

# Check bot container
BOT_STATUS=$(docker inspect --format='{{.State.Health.Status}}' proposal-assistant 2>/dev/null)
if [ "$BOT_STATUS" != "healthy" ]; then
    # Send alert via curl to Slack webhook
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🔴 CRITICAL: proposal-assistant container is '"$BOT_STATUS"'"}' \
        "$SLACK_WEBHOOK_URL"
fi

# Check Claude API
CLAUDE_OK=$(docker exec proposal-assistant python -c "from proposal_assistant.health import check_claude_api; r=check_claude_api(); print(r['status'])" 2>/dev/null)
if [ "$CLAUDE_OK" != "healthy" ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🔴 CRITICAL: Claude API is '"$CLAUDE_OK"'"}' \
        "$SLACK_WEBHOOK_URL"
fi

# Check disk usage
DISK_USAGE=$(df /opt/proposal-assistant --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_USAGE" -gt 80 ]; then
    curl -s -X POST -H 'Content-type: application/json' \
        --data '{"text":"🟡 WARNING: Disk usage at '"$DISK_USAGE"'%"}' \
        "$SLACK_WEBHOOK_URL"
fi
