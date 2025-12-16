import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import AbstractStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger

logger = get_logger("strategy_macd")

class MACDStrategy(AbstractStrategy):
    def __init__(self, name: str, symbols: List[str], fast_period=12, slow_period=26, signal_period=9):
        super().__init__(name, symbols)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.klines = {s: [] for s in symbols}
        self.min_klines = slow_period + signal_period + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        # Handle Kline Updates
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None
            
            # Append new candle
            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "close": event.close,
            })
            
            # Maintain window size
            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)
            
            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None
            
        df = pd.DataFrame(data)
        
        # Calculate MACD
        macd = ta.trend.MACD(
            close=df["close"], 
            window_slow=self.slow_period, 
            window_fast=self.fast_period, 
            window_sign=self.signal_period
        )
        
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        
        # Check Crossover (Last confirmed candle vs previous)
        # We use -1 as the most recent closed candle
        if len(df) < 2:
            return None
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Buy Signal: MACD Crosses Above Signal Line
        if prev["macd"] <= prev["macd_signal"] and curr["macd"] > curr["macd_signal"]:
            return Signal(SignalType.BUY, symbol, curr["close"], reason="MACD Crossover (Bullish)")

        # Sell Signal: MACD Crosses Below Signal Line
        if prev["macd"] >= prev["macd_signal"] and curr["macd"] < curr["macd_signal"]:
            return Signal(SignalType.SELL, symbol, curr["close"], reason="MACD Crossover (Bearish)")
            
        return None
