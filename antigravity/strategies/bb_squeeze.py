import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import BBSqueezeConfig
from antigravity.regime_detector import market_regime_detector, MarketRegime
from antigravity.logging import get_logger

logger = get_logger("strategy_bb_squeeze")

class BBSqueezeStrategy(BaseStrategy):
    def __init__(self, config: BBSqueezeConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        self.klines = {s: [] for s in symbols}
        self.min_klines = config.bb_period + 10

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

            # Regime Filter: Block if already Volatile (missed entry or too risky)
            regime_data = market_regime_detector.regimes.get(event.symbol)
            if regime_data and regime_data.regime == MarketRegime.VOLATILE:
                # Optional: Allow if we are already in a position (managed by Execution),
                # but for new signals, we want to enter BEFORE volatility spikes.
                # However, Breakout happens exactly when Volatility spikes.
                # So we block only if Volatility is EXTREME (e.g. late stage).
                # For now, strict check to adhere to "Regime Awareness".
                logger.debug("bb_squeeze_regime_block", symbol=event.symbol, regime="VOLATILE")
                return None

            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None

        df = pd.DataFrame(data)

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close=df["close"], window=self.config.bb_period, window_dev=self.config.bb_std)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()

        # Keltner Channels
        # Keltner Channel is EMA +/- (ATR * multiplier)
        # ta lib might not have direct Keltner, calculate manually
        df["ema"] = ta.trend.ema_indicator(df["close"], window=self.config.bb_period)
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=self.config.bb_period)

        df["kc_upper"] = df["ema"] + (df["atr"] * self.config.keltner_multiplier)
        df["kc_lower"] = df["ema"] - (df["atr"] * self.config.keltner_multiplier)

        curr = df.iloc[-1]

        # Squeeze On: BB is inside Keltner Channel
        squeeze_on = (curr["bb_upper"] < curr["kc_upper"]) and (curr["bb_lower"] > curr["kc_lower"])

        # Momentum for direction
        # Simple Momentum (Close - Close n periods ago)
        if len(df) > self.config.momentum_period:
            momentum = curr["close"] - df.iloc[-self.config.momentum_period]["close"]
        else:
            momentum = 0

        # We need to detect Squeeze Release.
        # For simplicity in this iteration: Signal if Squeeze was on recently and now Momentum is strong?
        # Actually, standard Squeeze indicator signals when momentum fires while/after squeeze.

        # Simplified Logic: If Squeeze is ON, prepare. If Squeeze breaks (BB expands) -> Trade.
        # But this requires tracking state "Squeeze Was On".

        # Let's implement State tracking here using `self.state`

        was_squeezed = self.state.get(symbol, {}).get("was_squeezed", False)

        if squeeze_on:
            self.state[symbol]["was_squeezed"] = True
            # No signal yet, just accumulation
            return None

        if was_squeezed and not squeeze_on:
            # Squeeze Fired!
            self.state[symbol]["was_squeezed"] = False

            if momentum > 0:
                return Signal(SignalType.BUY, symbol, curr["close"],
                              reason="BB Squeeze Fire (Long)",
                              leverage=self.config.leverage,
                              risk_percentage=self.config.risk_per_trade)
            elif momentum < 0:
                return Signal(SignalType.SELL, symbol, curr["close"],
                              reason="BB Squeeze Fire (Short)",
                              leverage=self.config.leverage,
                              risk_percentage=self.config.risk_per_trade)

        return None
