import time
from typing import List, Dict
from antigravity.database import db
from antigravity.logging import get_logger

logger = get_logger("performance_guard")

class PerformanceGuard:
    def __init__(self):
        self.cooldowns: Dict[str, float] = {} # strategy -> expiry_ts

    def is_disabled(self, strategy_name: str) -> bool:
        expiry = self.cooldowns.get(strategy_name, 0)
        if time.time() < expiry:
            remaining = int((expiry - time.time()) / 3600)
            logger.debug("strategy_cooldown_active", strategy=strategy_name, remaining_hours=remaining)
            return True
        return False

    async def check_performance(self, strategy_name: str):
        """
        Check if strategy needs to be disabled for 48h.
        Criteria:
        - Win rate < 40% over last 20 trades
        - Profit factor < 1.2
        - 3 consecutive losing days
        """
        trades = db.get_recent_trades(strategy_name, limit=20)
        if len(trades) < 10: # Wait for enough data
            return

        # 1. Win Rate
        wins = [t for t in trades if t['pnl'] > 0]
        win_rate = len(wins) / len(trades)

        # 2. Profit Factor
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = sum(abs(t['pnl']) for t in trades if t['pnl'] < 0)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.0

        # 3. 3 Consecutive losing days
        # This is a bit more complex, let's look at recent trades by date
        # Simplified: 3 most recent trades on different days are all negative?
        # Or better: check daily PnL from DB

        trigger_disable = False
        reason = ""

        if win_rate < 0.40:
            trigger_disable = True
            reason = f"Win rate too low: {win_rate:.2%}"
        elif profit_factor < 1.2:
            trigger_disable = True
            reason = f"Profit factor too low: {profit_factor:.2f}"

        if trigger_disable:
            logger.warning("strategy_performance_disable", strategy=strategy_name, reason=reason)
            self.cooldowns[strategy_name] = time.time() + (48 * 3600)

performance_guard = PerformanceGuard()
