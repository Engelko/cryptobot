from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
from antigravity.event import MarketDataEvent

class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class Signal:
    type: SignalType
    symbol: str
    price: Optional[float] = None
    quantity: Optional[float] = None
    reason: str = ""

class AbstractStrategy(ABC):
    def __init__(self, name: str, symbols: List[str]):
        self.name = name
        self.symbols = symbols
        self.is_active = False

    def start(self):
        self.is_active = True

    def stop(self):
        self.is_active = False

    @abstractmethod
    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        """
        Process incoming market data and potentially return a trading Signal.
        """
        pass
