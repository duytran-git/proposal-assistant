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
