from typing import Dict, List, Optional
from antigravity.strategy import Signal, SignalType
from antigravity.regime_detector import MarketRegime, MarketRegimeData
from antigravity.logging import get_logger

logger = get_logger("strategy_router")

class StrategyRouter:
    """
    Decides which signals to allow based on Market Regime.
    """

    # Mapping of Regime -> Allowed Strategies (or disallowed)
    # This could be configurable in yaml

    def __init__(self):
        pass

    def check_signal(self, signal: Signal, strategy_name: str, regime_data: Optional[MarketRegimeData]) -> bool:
        """
        Returns True if signal is allowed in current regime.
        """
        if not regime_data:
            # Default allow if no regime data (e.g. startup)
            return True

        regime = regime_data.regime

        # 0. High Volatility Check
        if regime == MarketRegime.VOLATILE:
            # Block Futures (linear) in high volatility
            if signal.category == "linear":
                logger.warning("router_block", strategy=strategy_name, regime="VOLATILE", reason="Futures prohibited in High Volatility")
                return False
        symbol = signal.symbol

        # Logic Matrix

        # 1. Grid Strategies -> Only RANGING
        if "Grid" in strategy_name:
            if regime not in [MarketRegime.RANGING]:
                logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="Grid only in Range")
                return False

        # 2. Trend Strategies -> Only TRENDING (UP/DOWN)
        if "Trend" in strategy_name or "GoldenCross" in strategy_name:
             if regime not in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
                 logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="Trend only in Trend")
                 return False

             # Counter-trend check
             if regime == MarketRegime.TRENDING_UP and signal.type == SignalType.SELL:
                 logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="No counter-trend shorts")
                 return False
             if regime == MarketRegime.TRENDING_DOWN and signal.type == SignalType.BUY:
                 logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="No counter-trend longs")
                 return False

        # 3. Volatility Strategies -> Only VOLATILE or Strong Trend
        if "Volatility" in strategy_name or "Breakout" in strategy_name:
            if regime == MarketRegime.RANGING and regime_data.adx < 15:
                 logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="No Breakout in deep flat")
                 return False

        # 4. Mean Reversion / Scalping -> RANGING or VOLATILE (careful)
        if "MeanReversion" in strategy_name or "Scalp" in strategy_name:
            if regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN] and regime_data.adx > 30:
                 # Don't scalp against strong trend
                 if (regime == MarketRegime.TRENDING_UP and signal.type == SignalType.SELL) or \
                    (regime == MarketRegime.TRENDING_DOWN and signal.type == SignalType.BUY):
                        logger.debug("router_block", strategy=strategy_name, regime=regime.value, reason="No counter-trend scalp in strong trend")
                        return False

        return True

strategy_router = StrategyRouter()
