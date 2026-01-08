from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
from antigravity.event import MarketDataEvent, OrderUpdateEvent
from antigravity.database import db
from antigravity.logging import get_logger

logger = get_logger("strategy")

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

class BaseStrategy(ABC):
    def __init__(self, name: str, symbols: List[str]):
        self.name = name
        self.symbols = symbols
        self.is_active = False
        self.state: Dict[str, Dict[str, Any]] = {s: {} for s in symbols}
        self.ticks_processed = 0
        self.last_indicator_status = "N/A"

    async def start(self):
        self.is_active = True
        await self.load_state()

    async def stop(self):
        self.is_active = False
        await self.save_state()

    async def load_state(self):
        for symbol in self.symbols:
            state = db.get_strategy_state(self.name, symbol)
            if state:
                self.state[symbol] = state
        logger.info("strategy_state_loaded", strategy=self.name)

    async def save_state(self):
        for symbol in self.symbols:
            if self.state.get(symbol):
                db.save_strategy_state(self.name, symbol, self.state[symbol])
        logger.info("strategy_state_saved", strategy=self.name)

    @abstractmethod
    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        """Process incoming market data and potentially return a trading Signal."""
        pass

    async def on_order_update(self, event: OrderUpdateEvent):
        """Handle order status updates (Filled, Cancelled). Override in subclasses."""
        pass

# Backward compatibility alias
AbstractStrategy = BaseStrategy
