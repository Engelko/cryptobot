import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import TrendConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_trend_improved")

class GoldenCrossImproved(BaseStrategy):
    """
    GoldenCrossImproved: Golden Cross with ADX Filter.
    """
    def __init__(self, config: TrendConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config

        # Use simple default if not present in config (though TrendConfig should have them)
        self.fast_period = getattr(config, 'fast_period', 50)
        self.slow_period = getattr(config, 'slow_period', 200)
        self.adx_threshold = 25.0 # Could be added to TrendConfig if needed, sticking to default/logic for now

        self.klines = {s: [] for s in symbols}
        # Ensure we have enough data for slow SMA + buffer
        self.min_klines = self.slow_period + 10

    def generate_signal(self, symbol: str, ma_short: float, ma_long: float,
                       current_price: float, adx_value: float) -> Optional[dict]:
        """
        Generates signal only if ADX confirms trend.
        """
        if adx_value < self.adx_threshold:
            return None # No trend

        if ma_short > ma_long and current_price > ma_short:
             return {"action": "BUY", "symbol": symbol, "strength": adx_value / 100}
        elif ma_short < ma_long and current_price < ma_short:
             return {"action": "SELL", "symbol": symbol, "strength": adx_value / 100}

        return None

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols: return None

            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "close": event.close,
                "high": event.high,
                "low": event.low
            })
            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)

            data = self.klines[event.symbol]
            if len(data) < self.min_klines: return None

            df = pd.DataFrame(data)

            # MA using Configured Periods
            df["fast_sma"] = ta.trend.sma_indicator(df["close"], window=self.fast_period)
            df["slow_sma"] = ta.trend.sma_indicator(df["close"], window=self.slow_period)

            # ADX
            adx_ind = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
            df["adx"] = adx_ind.adx()

            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # Crossover Check
            is_golden_cross = (prev["fast_sma"] <= prev["slow_sma"] and curr["fast_sma"] > curr["slow_sma"])
            is_death_cross = (prev["fast_sma"] >= prev["slow_sma"] and curr["fast_sma"] < curr["slow_sma"])

            if is_golden_cross or is_death_cross:
                 result = self.generate_signal(
                     symbol=event.symbol,
                     ma_short=curr["fast_sma"],
                     ma_long=curr["slow_sma"],
                     current_price=curr["close"],
                     adx_value=curr["adx"]
                 )

                 if result:
                     stype = SignalType.BUY if result["action"] == "BUY" else SignalType.SELL
                     return Signal(stype, event.symbol, event.close, reason="GoldenCross Improved")

        return None
