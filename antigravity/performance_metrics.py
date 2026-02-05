import numpy as np
from typing import List, Dict
from datetime import datetime, timedelta
from antigravity.database import db
from antigravity.logging import get_logger
from sqlalchemy import text

logger = get_logger("performance_metrics")

class PerformanceMetrics:
    def __init__(self, lookback_trades: int = 100, lookback_days: int = 30):
        self.lookback_trades = lookback_trades
        self.lookback_days = lookback_days

    def calculate_for_strategy(self, strategy_name: str) -> Dict[str, float]:
        """
        Calculate Sharpe Ratio, Profit Factor, and Expectancy for a strategy.
        Lookback: Last 100 trades or 30 days.
        """
        cutoff_date = datetime.now() - timedelta(days=self.lookback_days)
        query = text("""
            SELECT pnl, created_at FROM trades
            WHERE strategy = :strategy AND created_at >= :cutoff
            ORDER BY created_at DESC
            LIMIT :limit
        """)

        try:
            with db.engine.connect() as conn:
                result = conn.execute(query, {"strategy": strategy_name, "cutoff": cutoff_date, "limit": self.lookback_trades})
                trades = result.fetchall()
        except Exception as e:
            logger.error("metrics_query_failed", strategy=strategy_name, error=str(e))
            return {}

        if not trades:
            return {"sharpe": 0.0, "profit_factor": 0.0, "expectancy": 0.0, "win_rate": 0.0, "total_trades": 0}

        pnls = [float(t[0]) for t in trades]

        # 1. Profit Factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = sum(abs(p) for p in pnls if p < 0)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # 2. Win Rate
        wins = [p for p in pnls if p > 0]
        win_rate = len(wins) / len(pnls)

        # 3. Expectancy
        # Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        losses = [abs(p) for p in pnls if p < 0]
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        # 4. Sharpe Ratio
        if len(pnls) > 1:
            mean_pnl = np.mean(pnls)
            std_pnl = np.std(pnls)
            # Using trade-level sharpe (not time-level)
            sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
        else:
            sharpe = 0.0

        metrics = {
            "sharpe": round(sharpe, 3),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "win_rate": round(win_rate, 4),
            "total_trades": len(pnls)
        }

        logger.info("strategy_metrics_calculated", strategy=strategy_name, **metrics)
        return metrics

    def generate_full_report(self, strategies: List[str]) -> Dict[str, Dict]:
        report = {}
        for strat in strategies:
            report[strat] = self.calculate_for_strategy(strat)
        return report

performance_metrics = PerformanceMetrics()
