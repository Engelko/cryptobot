#!/bin/bash
set -e

APP_DIR="/opt/cryptobot"
PATCH_DIR="/opt/cryptobot/patches"

echo "=== Applying code modifications ==="

# 1. Modify risk.py
echo "Modifying antigravity/risk.py..."
sed -i '1i import time' "$APP_DIR/antigravity/risk.py"
sed -i '/from antigravity.event import event_bus/a from antigravity.metrics import metrics' "$APP_DIR/antigravity/risk.py"

# Add cache fields to __init__
sed -i '/self.last_reset_date = None/a\        # Cache fields\n        self._cached_balance = 0.0\n        self._balance_cache_time = 0\n        self._last_rejection_reason = None' "$APP_DIR/antigravity/risk.py"

# Add _fetch_balance_from_api method before _get_available_balance
sed -i '/async def _get_available_balance/i\    def _fetch_balance_from_api(self) -> float:\n        """Fetch fresh balance from API"""\n        if settings.SIMULATION_MODE:\n            return execution_manager.paper_broker.balance\n        \n        client = BybitClient()\n        try:\n            balance_data = await client.get_wallet_balance(coin="USDT")\n            if "totalWalletBalance" in balance_data:\n                return float(balance_data.get("totalWalletBalance", 0.0))\n            elif "coin" in balance_data:\n                for c in balance_data["coin"]:\n                    if c.get("coin") == "USDT":\n                        return float(c.get("walletBalance", 0.0))\n        finally:\n            await client.close()\n        \n        return 0.0\n' "$APP_DIR/antigravity/risk.py"

# Modify _get_available_balance to use cache
sed -i 's/if settings.SIMULATION_MODE:/# Use cached balance for 30 seconds\n        current_time = time.time()\n        if hasattr(self, '"'"'_cached_balance'"'"') and (current_time - self._balance_cache_time) < 30:\n            return self._cached_balance\n\n        balance = await self._fetch_balance_from_api()\n        self._cached_balance = balance\n        self._balance_cache_time = current_time\n        return balance\n\n        # Old code commented: if settings.SIMULATION_MODE:/' "$APP_DIR/antigravity/risk.py"

# Remove old implementation after the return statement
sed -i '/# Real Mode/,/return 0.0/d' "$APP_DIR/antigravity/risk.py"

echo "✓ risk.py modified"

echo "=== All modifications applied successfully ==="
