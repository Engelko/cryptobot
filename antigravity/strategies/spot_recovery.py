from typing import List, Optional, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType, TakeProfitLevel
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger
from antigravity.config import settings

logger = get_logger("spot_recovery_strategy")

class SpotRecoveryStrategy(BaseStrategy):
    """
    Spot DCA strategy for recovery mode.
    - Buy 30% initially.
    - Buy 30% at -3% drop.
    - Buy 40% at -6% drop.
    - Sell at +5% from average price.
    """
    def __init__(self, symbols: List[str]):
        super().__init__("SpotRecovery", symbols)
        self.active_dca: Dict[str, Dict] = {} # symbol -> {avg_price, total_qty, stage}

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if not isinstance(event, KlineEvent):
            return None

        symbol = event.symbol
        price = event.close

        # Check if we have an active DCA for this symbol
        if symbol not in self.active_dca:
            # We only start DCA if triggered externally or by some logic.
            # For now, let's say we start it if price is 'stable' and we are in recovery mode.
            # But the StrategyEngine will call this.
            return None

        dca = self.active_dca[symbol]
        avg_price = dca['avg_price']
        stage = dca['stage']

        # Check for DCA drops
        if stage == 1 and price <= avg_price * 0.97: # -3%
            dca['stage'] = 2
            logger.info("spot_dca_stage_2", symbol=symbol, price=price)
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                price=price,
                quantity=dca['initial_qty'] * 0.3 / 0.3, # This logic needs fixing
                reason="SPOT_DCA_STAGE_2",
                category="spot"
            )

        if stage == 2 and price <= avg_price * 0.94: # -6%
            dca['stage'] = 3
            logger.info("spot_dca_stage_3", symbol=symbol, price=price)
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                price=price,
                reason="SPOT_DCA_STAGE_3",
                category="spot"
            )

        # Check for Take Profit (+5%)
        if price >= avg_price * 1.05:
            logger.info("spot_dca_tp_hit", symbol=symbol, price=price, avg=avg_price)
            del self.active_dca[symbol]
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                price=price,
                reason="SPOT_DCA_TP",
                category="spot"
            )

        return None

    def start_dca(self, symbol: str, initial_qty: float, price: float):
        self.active_dca[symbol] = {
            "avg_price": price,
            "total_qty": initial_qty,
            "initial_qty_budget": initial_qty / 0.3, # If first buy is 30%
            "stage": 1
        }
