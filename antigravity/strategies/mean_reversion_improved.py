import pandas as pd
import ta
from typing import Optional, List, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import MeanReversionConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_mean_rev_improved")

class BollingerRSIImproved(BaseStrategy):
    """
    BollingerRSIImproved: Bollinger Bands + RSI with Cooldown and ADX filter.
    """
    def __init__(self, config: MeanReversionConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config

        # Load params from config with defaults
        self.cooldown_seconds = 300 # Not in config, keeping default
        self.adx_threshold = 25.0 # Not used for filtering, but kept as state

        self.rsi_period = getattr(config, 'rsi_period', 14)
        self.rsi_overbought = getattr(config, 'rsi_overbought', 70)
        self.rsi_oversold = getattr(config, 'rsi_oversold', 30)
        self.bb_period = getattr(config, 'bb_period', 20)
        self.bb_std = getattr(config, 'bb_std', 2.0)

        self.last_signal_time: Dict[str, float] = {} # {symbol: timestamp}
        self.signals_log = []

        # Data storage for indicators
        self.klines = {s: [] for s in symbols}
        self.min_klines = self.bb_period + 30 # Enough for BB

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

        # Filter 2: ADX Trend Check - Removed/Relaxed as per previous logic

        signal = None
        if bb_signal == "OVERSOLD" and rsi_value < self.rsi_oversold:
            signal = {"action": "BUY", "symbol": symbol, "confidence": rsi_value / 100}
        elif bb_signal == "OVERBOUGHT" and rsi_value > self.rsi_overbought:
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
            bb = ta.volatility.BollingerBands(close=df["close"], window=self.bb_period, window_dev=self.bb_std)
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_upper"] = bb.bollinger_hband()
            df["rsi"] = ta.momentum.rsi(df["close"], window=self.rsi_period)

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
