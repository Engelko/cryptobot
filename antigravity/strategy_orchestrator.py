import time
from typing import Dict, List, Optional, Any
from antigravity.logging import get_logger
from antigravity.regime_detector import MarketRegime, MarketRegimeData
from antigravity.strategy import AbstractStrategy
from antigravity.strategies.config import load_strategy_config

logger = get_logger("strategy_orchestrator")

class StrategyOrchestrator:
    def __init__(self):
        self.yaml_enabled_strategies: List[str] = []
        self._config_loaded = False
        self.last_evaluation = 0
        self.eval_interval = 300  # 5 minutes

    def _load_yaml_config(self):
        try:
            config = load_strategy_config("strategies.yaml")
            # Map strategy names as registered in main.py
            if config.bb_squeeze and config.bb_squeeze.enabled: self.yaml_enabled_strategies.append("BBSqueeze")
            if config.dynamic_risk_leverage and config.dynamic_risk_leverage.enabled: self.yaml_enabled_strategies.append("DynamicRiskLeverage")
            if config.grid and config.grid.enabled: self.yaml_enabled_strategies.append("Grid")
            if config.mean_reversion and config.mean_reversion.enabled: self.yaml_enabled_strategies.append("MeanReversion")
            if config.scalping and config.scalping.enabled: self.yaml_enabled_strategies.append("Scalping")
            if config.trend_following and config.trend_following.enabled: self.yaml_enabled_strategies.append("TrendFollowing")
            if config.volatility_breakout and config.volatility_breakout.enabled: self.yaml_enabled_strategies.append("VolatilityBreakout")
            self._config_loaded = True
            logger.info("orchestrator_config_loaded", enabled=self.yaml_enabled_strategies)
        except Exception as e:
            logger.error("orchestrator_config_load_failed", error=str(e))

    def evaluate(self, strategies: Dict[str, AbstractStrategy], regime_data_map: Dict[str, MarketRegimeData]):
        if not self._config_loaded:
            self._load_yaml_config()

        now = time.time()
        if now - self.last_evaluation < self.eval_interval:
            return

        self.last_evaluation = now

        # Determine representative regime (using BTCUSDT as proxy for general market)
        btc_regime_data = regime_data_map.get("BTCUSDT")
        if not btc_regime_data:
            # Fallback to the first available regime if BTC not available
            if regime_data_map:
                btc_regime_data = list(regime_data_map.values())[0]
            else:
                return

        regime = btc_regime_data.regime
        logger.info("orchestrator_evaluating", regime=regime.value, btc_adx=btc_regime_data.adx)

        for name, strategy in strategies.items():
            # Only manage strategies that were enabled in YAML
            if name not in self.yaml_enabled_strategies:
                if name != "SpotRecovery":
                    continue

            should_run = False
            if regime == MarketRegime.TRENDING_UP:
                if name in ["TrendFollowing", "DynamicRiskLeverage"]:
                    should_run = True
            elif regime == MarketRegime.TRENDING_DOWN:
                if name in ["TrendFollowing", "DynamicRiskLeverage"]:
                    should_run = True
            elif regime == MarketRegime.RANGING:
                if name in ["MeanReversion", "Grid"]:
                    should_run = True
            elif regime == MarketRegime.VOLATILE:
                if name == "SpotRecovery":
                    should_run = True
            elif regime == MarketRegime.UNCERTAIN:
                # GoldenCross (TrendFollowing) in UNCERTAIN at ADX > 20
                if name == "TrendFollowing" and btc_regime_data.adx > 20:
                     should_run = True
                else:
                     should_run = False

            if name != "SpotRecovery":
                if strategy.is_active != should_run:
                    logger.info("orchestrator_strategy_toggle", strategy=name, active=should_run, regime=regime.value)
                    strategy.is_active = should_run

orchestrator = StrategyOrchestrator()
