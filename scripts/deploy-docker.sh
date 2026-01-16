#!/bin/bash
set -e

APP_DIR="/opt/cryptobot"
BACKUP_DIR="/opt/cryptobot/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== Docker Compose Deployment at $TIMESTAMP ==="

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
echo "Backing up database..."
cp $APP_DIR/storage/data.db $BACKUP_DIR/data.db.$TIMESTAMP
echo "Backup: $BACKUP_DIR/data.db.$TIMESTAMP"

# Apply SQL changes (before restart)
echo "Applying SQL changes..."
if [ -f "$APP_DIR/storage/add_indexes.sql" ]; then
    sqlite3 $APP_DIR/storage/data.db < $APP_DIR/storage/add_indexes.sql
    echo "✓ Indexes applied"
fi

if [ -f "$APP_DIR/storage/create_positions_table.sql" ]; then
    sqlite3 $APP_DIR/storage/data.db < $APP_DIR/storage/create_positions_table.sql
    echo "✓ Positions table created"
fi

# Verify changes
echo "Verifying database changes..."
INDEX_COUNT=$(sqlite3 $APP_DIR/storage/data.db "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';")
echo "Indexes in DB: $INDEX_COUNT"

POSITION_TABLE=$(sqlite3 $APP_DIR/storage/data.db "SELECT name FROM sqlite_master WHERE type='table' AND name='positions';")
if [ -n "$POSITION_TABLE" ]; then
    echo "✓ Positions table exists"
else
    echo "✗ ERROR: Positions table not found!"
    exit 1
fi

# Git commit before restart
echo "Committing changes to git..."
cd $APP_DIR
git add .
git commit -m "Optimization deployment $TIMESTAMP" || echo "Nothing to commit"

# Restart containers
echo "Restarting Docker Compose..."
docker-compose down
sleep 3
docker-compose up -d --build

# Wait for startup
echo "Waiting for services to start..."
sleep 15

# Health check
echo "Running health check..."
ENGINE_STATUS=$(docker-compose ps -q engine | xargs docker inspect --format='{{.State.Status}}' 2>/dev/null || echo "stopped")
DASHBOARD_STATUS=$(docker-compose ps -q dashboard | xargs docker inspect --format='{{.State.Status}}' 2>/dev/null || echo "stopped")

if [ "$ENGINE_STATUS" = "running" ]; then
    echo "✓ Engine container is running"
else
    echo "✗ Engine container failed to start!"
    docker-compose logs --tail=50 engine
    exit 1
fi

if [ "$DASHBOARD_STATUS" = "running" ]; then
    echo "✓ Dashboard container is running"
else
    echo "✗ Dashboard container failed to start!"
    docker-compose logs --tail=50 dashboard
    exit 1
fi

echo "=== Deployment completed successfully ==="
echo ""
echo "Monitoring commands:"
echo "  - Logs: docker-compose logs -f"
echo "  - Engine logs: docker-compose logs -f engine"
echo "  - Dashboard logs: docker-compose logs -f dashboard"
echo "  - Status: docker-compose ps"
echo "  - Monitor: ./scripts/monitor-docker.sh"
echo ""
echo "To rollback: ./scripts/rollback-docker.sh"
