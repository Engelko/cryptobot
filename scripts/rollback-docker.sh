#!/bin/bash
set -e

APP_DIR="/opt/cryptobot"

echo "=== Docker Compose Rollback ==="

# Stop containers
echo "Stopping containers..."
cd $APP_DIR
docker-compose down

# Revert code changes
echo "Reverting code changes..."
git status
echo "Run one of the following:"
echo "  git checkout -- .        (to revert ALL changes)"
echo "  git revert <commit>       (to revert specific commit)"

# Restore database if backup exists
LATEST_BACKUP=$(ls -t $APP_DIR/backups/data.db.* 2>/dev/null | head -1)
if [ -n "$LATEST_BACKUP" ]; then
    echo "Restoring database from: $LATEST_BACKUP"
    cp "$LATEST_BACKUP" $APP_DIR/storage/data.db
    echo "✓ Database restored"
else
    echo "⚠ WARNING: No database backup found!"
fi

# Restart containers
echo "Restarting containers..."
docker-compose up -d

sleep 10

echo "=== Rollback completed ==="
echo "Check status: docker-compose ps"
