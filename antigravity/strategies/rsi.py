import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import AbstractStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.logging import get_logger

logger = get_logger("strategy_rsi")

class RSIStrategy(AbstractStrategy):
    def __init__(self, name: str, symbols: List[str], period=14, overbought=70, oversold=30):
        super().__init__(name, symbols)
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        self.klines = {s: [] for s in symbols}
        self.min_klines = period + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None
            
            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "close": event.close
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
        
        # Calculate RSI
        rsi_ind = ta.momentum.RSIIndicator(close=df["close"], window=self.period)
        df["rsi"] = rsi_ind.rsi()
        
        curr_rsi = df.iloc[-1]["rsi"]
        curr_price = df.iloc[-1]["close"]
        
        if curr_rsi < self.oversold:
            return Signal(SignalType.BUY, symbol, curr_price, reason=f"RSI Oversold ({curr_rsi:.2f})")
            
        if curr_rsi > self.overbought:
            return Signal(SignalType.SELL, symbol, curr_price, reason=f"RSI Overbought ({curr_rsi:.2f})")
            
        return None
