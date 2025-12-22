import asyncio
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Type, Awaitable
from datetime import datetime
import uuid
from antigravity.logging import get_logger

logger = get_logger("event_bus")

@dataclass
class Event:
    """Base class for all system events."""
    payload: Any = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def name(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["timestamp"] = self.timestamp.isoformat()
        return d

@dataclass
class MarketDataEvent(Event):
    """Event for real-time market data updates (Orderbook, Trades)."""
    topic: str = ""
    data: Any = None

@dataclass
class KlineEvent(MarketDataEvent):
    """Event for completed Kline (Candlestick) updates."""
    symbol: str = ""
    interval: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    timestamp: int = 0

@dataclass
class SentimentEvent(Event):
    """Event for AI Sentiment Analysis results."""
    score: float = 0.0 # -1.0 to 1.0
    reasoning: str = ""
    model: str = ""

class EventBus:
    """
    Asynchronous Event Bus using asyncio.Queue for decoupling components.
    """
    def __init__(self):
        self._subscribers: Dict[Type[Event], List[Callable[[Event], Awaitable[None]]]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False
        self._worker_task: asyncio.Task | None = None

    def subscribe(self, event_type: Type[Event], handler: Callable[[Event], Awaitable[None]]):
        """Register a handler for a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("subscriber_added", event_type=event_type.__name__, handler=handler.__name__)

    async def publish(self, event: Event):
        """Publish an event to the queue."""
        await self._queue.put(event)

    async def _worker(self):
        """Background worker to process events."""
        logger.info("event_bus_started")
        while self._running:
            try:
                event = await self._queue.get()
                
                # Direct match
                if type(event) in self._subscribers:
                    handlers = self._subscribers[type(event)]
                    await asyncio.gather(*[h(event) for h in handlers], return_exceptions=True)
                
                # Check for base classes (for polymorphism)
                for sub_type, handlers in self._subscribers.items():
                    if sub_type != type(event) and isinstance(event, sub_type):
                         await asyncio.gather(*[h(event) for h in handlers], return_exceptions=True)

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("event_processing_error", error=str(e))

    def start(self):
        """Start the event processing loop."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        """Stop the event processing loop."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("event_bus_stopped")

# Global EventBus Instance
event_bus = EventBus()

def on_event(event_type: Type[Event]):
    """Decorator to register a function as an event handler."""
    def decorator(func: Callable[[Event], Awaitable[None]]):
        event_bus.subscribe(event_type, func)
        return func
    return decorator
