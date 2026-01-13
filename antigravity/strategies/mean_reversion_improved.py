import pandas as pd
import ta
from typing import Optional, List, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger

logger = get_logger("strategy_mean_rev_improved")

class BollingerRSIImproved(BaseStrategy):
    """
    BollingerRSIImproved: Bollinger Bands + RSI with Cooldown and ADX filter.
    """
    def __init__(self, symbols: List[str], cooldown_seconds: int = 300, adx_threshold: float = 25.0):
        super().__init__("BollingerRSIImproved", symbols)
        self.cooldown_seconds = cooldown_seconds
        self.adx_threshold = adx_threshold
        self.last_signal_time: Dict[str, float] = {} # {symbol: timestamp}
        self.signals_log = []

        # Data storage for indicators
        self.klines = {s: [] for s in symbols}
        self.min_klines = 50 # Enough for BB(20) and ADX(14)

    def generate_signal(self, symbol: str, bb_signal: str, rsi_value: float,
                       current_time: float, adx_value: float) -> Optional[dict]:
        """
        Generates a signal with filters (Cooldown & ADX).
        Note: This method is designed to be testable without full event loop.
        """
        # Filter 1: Cooldown
        if symbol in self.last_signal_time:
            if current_time - self.last_signal_time[symbol] < self.cooldown_seconds:
                return None

        # Filter 2: ADX Trend Check
        # Mean Reversion (BollingerRSI) works BEST in Sideways markets (Low ADX).
        # Previously we required ADX > 25, which killed the strategy in flat markets.
        # We now ALLOW trading in low ADX. In fact, we might prefer it.
        # So we REMOVE the filter that blocks low ADX.
        # If anything, we could filter out High ADX, but for now we just remove the restriction.

        signal = None
        if bb_signal == "OVERSOLD" and rsi_value < 30:
            signal = {"action": "BUY", "symbol": symbol, "confidence": rsi_value / 100}
        elif bb_signal == "OVERBOUGHT" and rsi_value > 70:
            signal = {"action": "SELL", "symbol": symbol, "confidence": (100 - rsi_value) / 100}

        if signal:
            self.last_signal_time[symbol] = current_time
            self.signals_log.append(signal)
            return signal

        return None

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols: return None

            # Store Kline
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

            # Calculate Indicators
            bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2.0)
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_upper"] = bb.bollinger_hband()
            df["rsi"] = ta.momentum.rsi(df["close"], window=14)

            # ADX
            adx_ind = ta.trend.ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
            df["adx"] = adx_ind.adx()

            curr = df.iloc[-1]
            current_time = event.timestamp / 1000.0 # timestamp is usually ms in this bot

            bb_signal = "NEUTRAL"
            if curr["close"] < curr["bb_lower"]: bb_signal = "OVERSOLD"
            if curr["close"] > curr["bb_upper"]: bb_signal = "OVERBOUGHT"

            result = self.generate_signal(
                symbol=event.symbol,
                bb_signal=bb_signal,
                rsi_value=curr["rsi"],
                current_time=current_time,
                adx_value=curr["adx"]
            )

            if result:
                stype = SignalType.BUY if result["action"] == "BUY" else SignalType.SELL
                return Signal(stype, event.symbol, event.close, reason="BollingerRSI Improved")

        return None
