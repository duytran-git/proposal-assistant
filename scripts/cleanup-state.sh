#!/bin/bash
DATA_DIR="/opt/proposal-assistant/data/threads"

# Remove DONE threads older than 90 days
DONE_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +90 -exec grep -l '"state": "DONE"' {} \; -delete

# Remove ERROR threads older than 30 days
ERROR_COUNT=$(find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; | wc -l)
find "$DATA_DIR" -name "*.json" -mtime +30 -exec grep -l '"state": "ERROR"' {} \; -delete

echo "$(date): Cleaned $DONE_COUNT done + $ERROR_COUNT error threads" >> /var/log/proposal-assistant-cleanup.log
