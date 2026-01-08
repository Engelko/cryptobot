import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import MeanReversionConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_mean_rev")

class MeanReversionStrategy(BaseStrategy):
    def __init__(self, config: MeanReversionConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        self.klines = {s: [] for s in symbols}
        self.min_klines = max(config.bb_period, config.rsi_period) + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None

            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "close": event.close,
            })

            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)

            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None

        df = pd.DataFrame(data)

        # Bollinger Bands
        indicator_bb = ta.volatility.BollingerBands(close=df["close"], window=self.config.bb_period, window_dev=self.config.bb_std)
        df["bb_lower"] = indicator_bb.bollinger_lband()
        df["bb_upper"] = indicator_bb.bollinger_hband()

        # RSI
        df["rsi"] = ta.momentum.rsi(df["close"], window=self.config.rsi_period)

        curr = df.iloc[-1]

        # Buy: Price < Lower BB AND RSI < Oversold
        if curr["close"] < curr["bb_lower"] and curr["rsi"] < self.config.rsi_oversold:
            return Signal(SignalType.BUY, symbol, curr["close"], reason="Oversold (BB+RSI)")

        # Sell: Price > Upper BB AND RSI > Overbought
        if curr["close"] > curr["bb_upper"] and curr["rsi"] > self.config.rsi_overbought:
            return Signal(SignalType.SELL, symbol, curr["close"], reason="Overbought (BB+RSI)")

        # Telemetry
        self.last_indicator_status = f"RSI={curr['rsi']:.2f} BB_Low={curr['bb_lower']:.2f}"
        self.ticks_processed += 1
        if self.ticks_processed % 10 == 0:
             logger.info("strategy_heartbeat", name=self.name, symbol=symbol, status=self.last_indicator_status)

        return None
