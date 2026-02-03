from typing import List, Optional, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType, TakeProfitLevel
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger
from antigravity.config import settings
from antigravity.regime_detector import MarketRegime, market_regime_detector

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

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if not isinstance(event, KlineEvent):
            return None

        symbol = event.symbol
        price = event.close

        # Access active_dca from persisted state
        dca = self.state.get(symbol, {})

        # 1. Trigger Logic for First Buy
        if not dca or not dca.get("active"):
            from antigravity.engine import strategy_engine
            from antigravity.risk import TradingMode

            risk_manager = strategy_engine.risk_manager
            regime_data = market_regime_detector.regimes.get(symbol)

            # Trigger if in RECOVERY mode and market is VOLATILE
            if risk_manager.trading_mode == TradingMode.RECOVERY and \
               regime_data and regime_data.regime == MarketRegime.VOLATILE:

                logger.info("spot_recovery_trigger", symbol=symbol, price=price)

                # Initialize DCA state
                await self.start_dca(symbol, initial_qty=0.0, price=price) # quantity will be set by RiskManager

                return Signal(
                    symbol=symbol,
                    type=SignalType.BUY,
                    price=price,
                    reason="SPOT_RECOVERY_START",
                    category="spot"
                )
            return None

        avg_price = dca['avg_price']
        stage = dca['stage']

        # Check for DCA drops
        if stage == 1 and price <= avg_price * 0.97: # -3%
            dca['stage'] = 2
            logger.info("spot_dca_stage_2", symbol=symbol, price=price)
            await self.save_state()
            return Signal(
                symbol=symbol,
                type=SignalType.BUY,
                price=price,
                reason="SPOT_DCA_STAGE_2",
                category="spot"
            )

        if stage == 2 and price <= avg_price * 0.94: # -6%
            dca['stage'] = 3
            logger.info("spot_dca_stage_3", symbol=symbol, price=price)
            await self.save_state()
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
            self.state[symbol] = {"active": False}
            await self.save_state()
            return Signal(
                symbol=symbol,
                type=SignalType.SELL,
                price=price,
                reason="SPOT_DCA_TP",
                category="spot"
            )

        return None

    async def on_order_update(self, event):
        """Update state when Spot DCA orders are filled."""
        if event.order_status != "Filled":
            return

        symbol = event.symbol
        dca = self.state.get(symbol, {})
        if not dca or not dca.get("active"):
            return

        # Update Average Price and Total Quantity
        price = event.price
        qty = event.qty

        current_total_qty = dca.get("total_qty", 0.0)
        current_avg_price = dca.get("avg_price", 0.0)

        new_total_qty = current_total_qty + qty
        if new_total_qty > 0:
            new_avg_price = (current_avg_price * current_total_qty + price * qty) / new_total_qty
            dca["avg_price"] = new_avg_price
            dca["total_qty"] = new_total_qty

            logger.info("spot_recovery_state_updated", symbol=symbol, avg_price=new_avg_price, total_qty=new_total_qty)
            await self.save_state()

    async def start_dca(self, symbol: str, initial_qty: float, price: float):
        self.state[symbol] = {
            "active": True,
            "avg_price": price,
            "total_qty": initial_qty,
            "stage": 1
        }
        await self.save_state()
