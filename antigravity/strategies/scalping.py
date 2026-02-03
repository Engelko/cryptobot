import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import ScalpingConfig
from antigravity.regime_detector import market_regime_detector, MarketRegime
from antigravity.logging import get_logger

logger = get_logger("strategy_scalping")

class ScalpingStrategy(BaseStrategy):
    def __init__(self, config: ScalpingConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        self.klines = {s: [] for s in symbols}
        self.min_klines = config.k_period + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None

            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "high": event.high,
                "low": event.low,
                "close": event.close,
            })

            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)

            # Regime Filter: Block if Volatile (Risk of slippage/whipsaw)
            regime_data = market_regime_detector.regimes.get(event.symbol)
            if regime_data and regime_data.regime == MarketRegime.VOLATILE:
                logger.debug("scalping_regime_block", symbol=event.symbol, regime="VOLATILE")
                return None

            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None

        df = pd.DataFrame(data)

        # Stochastic
        stoch = ta.momentum.StochasticOscillator(
            high=df["high"], low=df["low"], close=df["close"],
            window=self.config.k_period, smooth_window=self.config.d_period
        )
        df["k"] = stoch.stoch()
        df["d"] = stoch.stoch_signal()

        if len(df) < 2:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # Buy: K crosses above D in oversold zone
        if prev["k"] < prev["d"] and curr["k"] > curr["d"] and curr["k"] < self.config.oversold:
            return Signal(SignalType.BUY, symbol, curr["close"], reason="Stoch Buy", leverage=self.config.leverage)

        # Sell: K crosses below D in overbought zone
        if prev["k"] > prev["d"] and curr["k"] < curr["d"] and curr["k"] > self.config.overbought:
            return Signal(SignalType.SELL, symbol, curr["close"], reason="Stoch Sell", leverage=self.config.leverage)

        return None
