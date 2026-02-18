from typing import Dict, List, Optional
from antigravity.strategy import Signal, SignalType
from antigravity.regime_detector import MarketRegime, MarketRegimeData
from antigravity.logging import get_logger

logger = get_logger("strategy_router")

class StrategyRouter:
    """
    Decides which signals to allow based on Market Regime.
    """

    def __init__(self):
        pass

    def check_signal(self, signal: Signal, strategy_name: str, regime_data: Optional[MarketRegimeData]) -> tuple[bool, str]:
        from antigravity.profiles import get_current_profile
        
        profile = get_current_profile()
        
        if not profile.enable_regime_filter:
            logger.debug("router_regime_filter_disabled", profile=profile.name)
            return True, ""
        
        if not regime_data:
            return True, ""

        regime = regime_data.regime

        if regime == MarketRegime.VOLATILE:
            logger.debug("router_volatile_pass", strategy=strategy_name, regime="VOLATILE", reason="Volatility detected, passing to RiskManager for possible conversion to Spot")
        symbol = signal.symbol

        if "Grid" in strategy_name:
            if regime not in [MarketRegime.RANGING]:
                reason = f"Grid only in RANGING (current: {regime.value})"
                logger.debug("router_block", strategy=strategy_name, reason=reason)
                return False, reason

        if "Trend" in strategy_name or "GoldenCross" in strategy_name:
             if strategy_name == "GoldenCross" and regime == MarketRegime.UNCERTAIN:
                 if regime_data and regime_data.adx > 20:
                     return True, ""

             if regime not in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.VOLATILE]:
                 reason = f"Trend only in TRENDING or VOLATILE (current: {regime.value})"
                 logger.debug("router_block", strategy=strategy_name, reason=reason)
                 return False, reason

             if regime == MarketRegime.TRENDING_UP and signal.type == SignalType.SELL:
                 reason = f"No counter-trend shorts in {regime.value}"
                 logger.debug("router_block", strategy=strategy_name, reason=reason)
                 return False, reason
             if regime == MarketRegime.TRENDING_DOWN and signal.type == SignalType.BUY:
                 reason = f"No counter-trend longs in {regime.value}"
                 logger.debug("router_block", strategy=strategy_name, reason=reason)
                 return False, reason

        if "Volatility" in strategy_name or "Breakout" in strategy_name:
            if regime == MarketRegime.RANGING and regime_data.adx < 15:
                 reason = f"No Breakout in deep flat (ADX: {regime_data.adx})"
                 logger.debug("router_block", strategy=strategy_name, reason=reason)
                 return False, reason

        if "MeanReversion" in strategy_name or "Scalp" in strategy_name:
            if regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN] and regime_data.adx > 30:
                 if (regime == MarketRegime.TRENDING_UP and signal.type == SignalType.SELL) or \
                    (regime == MarketRegime.TRENDING_DOWN and signal.type == SignalType.BUY):
                        reason = f"No counter-trend scalp in strong trend (ADX: {regime_data.adx})"
                        logger.debug("router_block", strategy=strategy_name, reason=reason)
                        return False, reason

        return True, ""

strategy_router = StrategyRouter()
