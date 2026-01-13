import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger

logger = get_logger("strategy_trend_improved")

class GoldenCrossImproved(BaseStrategy):
    """
    GoldenCrossImproved: Golden Cross with ADX Filter.
    """
    def __init__(self, symbols: List[str], adx_threshold: float = 25.0):
        super().__init__("GoldenCrossImproved", symbols)
        self.adx_threshold = adx_threshold

        self.klines = {s: [] for s in symbols}
        self.min_klines = 210 # 200 SMA + buffer

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

            # MA
            df["fast_sma"] = ta.trend.sma_indicator(df["close"], window=50)
            df["slow_sma"] = ta.trend.sma_indicator(df["close"], window=200)

            # ADX
            adx_ind = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
            df["adx"] = adx_ind.adx()

            curr = df.iloc[-1]
            prev = df.iloc[-2] # Current implementation of generate_signal is snapshot-based,
                               # but Golden Cross is crossover-based.
                               # Prompt: "if ma_short > ma_long ... return BUY".
                               # This checks STATE, not CROSSOVER.
                               # To prevent spamming signals every tick while crossed, we should check previous state?
                               # The prompt's example code:
                               # if ma_short > ma_long ... return BUY.
                               # This implies it returns a signal CONTINUOUSLY while in state?
                               # That would spam orders.
                               # Wait, the prompt Rec #2 says "GoldenCross generates signals on sideways market...".
                               # The example code provided in prompt `generate_signal` is stateless (just checks current values).
                               # However, standard practice is Crossover.
                               # I will stick to the prompt's `generate_signal` logic for the method,
                               # BUT in `on_market_data` I should probably check for the *Cross* event to avoid spam,
                               # OR rely on the Engine to handle duplicate signals (which it might not).
                               # Actually, looking at the original `trend.py`:
                               # `if prev["fast_sma"] <= prev["slow_sma"] and curr["fast_sma"] > curr["slow_sma"]`
                               # It checks CROSSOVER.
                               # The prompt's "Improved" code snippet lacks the `prev` check.
                               # I should probably add the crossover logic to `generate_signal` or `on_market_data`.
                               # I'll add `prev_ma_short`, `prev_ma_long` to `generate_signal` arguments to allow crossover check.
                               # But the prompt's `generate_signal` signature is fixed: (symbol, ma_short, ma_long, current_price, adx_value).
                               # It doesn't have prev values.
                               # So the prompt code is likely a simplified example or implies "State-based" signal.
                               # If I implement state-based, I need a mechanism to prevent repeating signals.
                               # I'll assume the caller (on_market_data) handles the "Cross" detection
                               # and only calls `generate_signal` when a cross happens?
                               # NO, `generate_signal` returns the dict.
                               # I will implement `generate_signal` as requested (stateless check),
                               # BUT inside `on_market_data` I will only call it if a CROSSOVER occurred.

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
