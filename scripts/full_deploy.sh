#!/bin/bash
set -e

APP_DIR="/opt/cryptobot"
echo "=== Full deployment script ==="

# 1. Stop containers
echo "Step 1: Stopping docker containers..."
cd $APP_DIR
docker-compose down
sleep 5

# 2. Copy files to modify (they are owned by root)
echo "Step 2: Copying files to temporary location..."
mkdir -p $APP_DIR/temp_modifications
cp $APP_DIR/antigravity/risk.py $APP_DIR/temp_modifications/risk.py
cp $APP_DIR/antigravity/execution.py $APP_DIR/temp_modifications/execution.py
cp $APP_DIR/antigravity/database.py $APP_DIR/temp_modifications/database.py
cp $APP_DIR/main.py $APP_DIR/temp_modifications/main.py
cp $APP_DIR/dashboard.py $APP_DIR/temp_modifications/dashboard.py

# 3. Apply modifications using python
echo "Step 3: Applying modifications to temporary files..."
python3 << 'PYTHON_SCRIPT'
import sys
import re

def modify_risk_py(path):
    with open(path, 'r') as f:
        content = f.read()
    
    # Add time import
    if 'import time' not in content:
        content = content.replace('from datetime import datetime, timezone', 'import time\nfrom datetime import datetime, timezone')
    
    # Add metrics import
    if 'from antigravity.metrics import metrics' not in content:
        content = content.replace('from antigravity.event import event_bus, TradeClosedEvent, on_event',
                                 'from antigravity.event import event_bus, TradeClosedEvent, on_event\nfrom antigravity.metrics import metrics')
    
    # Add cache fields to __init__
    if 'self._cached_balance = 0.0' not in content:
        content = content.replace('self.last_reset_date = None',
                                 'self.last_reset_date = None\n\n        # Cache fields\n        self._cached_balance = 0.0\n        self._balance_cache_time = 0\n        self._last_rejection_reason = None')
    
    # Add _fetch_balance_from_api method
    if 'def _fetch_balance_from_api' not in content:
        fetch_method = '''
    def _fetch_balance_from_api(self) -> float:
        """Fetch fresh balance from API"""
        if settings.SIMULATION_MODE:
            return execution_manager.paper_broker.balance
        
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            if "totalWalletBalance" in balance_data:
                return float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))
        finally:
            await client.close()
        
        return 0.0
'''
        content = content.replace('async def _get_available_balance(self) -> float:', f'{fetch_method}\n\n    async def _get_available_balance(self) -> float:')
    
    # Modify _get_available_balance to use cache
    if 'current_time = time.time()' not in content:
        old_impl = '''    async def _get_available_balance(self) -> float:
        """
        Fetch available USDT balance.
        If Simulation Mode, fetch from PaperBroker.
        If Real Mode, fetch from Bybit API.
        """
        if settings.SIMULATION_MODE:
            return execution_manager.paper_broker.balance

        # Real Mode
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            # Logic similar to RealBroker._parse_available_balance
            if "totalWalletBalance" in balance_data:
                 return float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                 for c in balance_data["coin"]:
                     if c.get("coin") == "USDT":
                         return float(c.get("walletBalance", 0.0))
        except Exception as e:
            logger.error("risk_balance_fetch_error", error=str(e))
        finally:
            await client.close()

        return 0.0'''
        
        new_impl = '''    async def _get_available_balance(self) -> float:
        """
        Fetch available USDT balance with 30-second cache.
        If Simulation Mode, fetch from PaperBroker.
        If Real Mode, fetch from Bybit API.
        """
        # Use cached balance for 30 seconds
        current_time = time.time()
        if hasattr(self, '_cached_balance') and (current_time - self._balance_cache_time) < 30:
            return self._cached_balance

        balance = await self._fetch_balance_from_api()
        self._cached_balance = balance
        self._balance_cache_time = current_time
        return balance'''
        
        content = content.replace(old_impl, new_impl)
    
    with open(path, 'w') as f:
        f.write(content)

# Apply modifications
modify_risk_py('/opt/cryptobot/temp_modifications/risk.py')

print('All modifications applied successfully')
PYTHON_SCRIPT

# 4. Copy modified files back to original location
echo "Step 4: Copying modified files back..."
sudo cp $APP_DIR/temp_modifications/risk.py $APP_DIR/antigravity/risk.py
sudo cp $APP_DIR/temp_modifications/execution.py $APP_DIR/antigravity/execution.py
sudo cp $APP_DIR/temp_modifications/database.py $APP_DIR/antigravity/database.py
sudo cp $APP_DIR/temp_modifications/main.py $APP_DIR/main.py
sudo cp $APP_DIR/temp_modifications/dashboard.py $APP_DIR/dashboard.py

# 5. Restart containers
echo "Step 5: Restarting docker containers..."
docker-compose up -d --build

# 6. Wait for startup
echo "Step 6: Waiting for containers to start..."
sleep 20

# 7. Health check
echo "Step 7: Health check..."
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

echo ""
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
