from antigravity.config import settings
from antigravity.strategy import Signal, SignalType
from antigravity.logging import get_logger

logger = get_logger("risk_manager")

class RiskManager:
    def __init__(self):
        self.max_daily_loss = settings.MAX_DAILY_LOSS
        self.max_position_size = settings.MAX_POSITION_SIZE
        self.current_daily_loss = 0.0

    def check_signal(self, signal: Signal) -> bool:
        """
        Validate if the signal matches risk parameters.
        Returns True if safe, False if blocked.
        """
        # 1. Check Daily Loss Limit
        if self.current_daily_loss >= self.max_daily_loss:
            logger.warning("risk_block", reason="daily_loss_limit_exceeded", 
                           current_loss=self.current_daily_loss, limit=self.max_daily_loss)
            return False

        # 2. Check Position Size (Estimated via price * quantity if quantity provided)
        # For now, we assume strategy might not provide quantity, so we skip if not present
        # In H05 strategies return price, but quantity is None. 
        # H10 execution logic would calculate quantity. 
        # Here we just log a check placeholder.
        if signal.quantity and signal.price:
            notional = signal.quantity * signal.price
            if notional > self.max_position_size:
                logger.warning("risk_block", reason="max_position_size_exceeded", 
                               notional=notional, limit=self.max_position_size)
                return False

        return True

    def update_metrics(self, realized_pnl: float):
        """
        Update risk metrics after a trade closes.
        """
        if realized_pnl < 0:
            self.current_daily_loss += abs(realized_pnl)
        
        # Reset if new day (simplistic logic for now)
        # Real impl would reset at 00:00 UTC
        pass
