import asyncio
import signal
from antigravity.logging import configure_logging, get_logger
from antigravity.engine import strategy_engine
from antigravity.event import event_bus
from antigravity.strategies.macd import MACDStrategy
from antigravity.strategies.rsi import RSIStrategy
from antigravity.copilot import AICopilot
from antigravity.execution import execution_manager
from antigravity.websocket_client import BybitWebSocket

logger = get_logger("main")

# Global reference to keep the websocket client alive
ws_client = None

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info("system_shutdown_initiated", signal=signal.name)
    
    if ws_client:
        await ws_client.close()

    await strategy_engine.stop()
    await event_bus.stop()
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    logger.info("system_shutdown_complete", tasks_cancelled=len(tasks))
    loop.stop()

async def main():
    # 1. Setup Logging
    configure_logging()
    logger.info("system_startup")

    # 2. Initialize Components
    
    # Register Strategies
    from antigravity.config import settings
    symbols = settings.TRADING_SYMBOLS
    active_strategies = settings.ACTIVE_STRATEGIES

    if "MACD_Trend" in active_strategies:
        # MACD Params: 12, 26, 9
        macd = MACDStrategy(name="MACD_Trend", symbols=symbols)
        strategy_engine.register_strategy(macd)
    
    if "RSI_Reversion" in active_strategies:
        # RSI Params: 14, 70, 30
        rsi = RSIStrategy(name="RSI_Reversion", symbols=symbols)
        strategy_engine.register_strategy(rsi)
    
    # Initialize Engine & Event Bus
    event_bus.start()
    await strategy_engine.start()
    
    # Start AI Copilot
    copilot = AICopilot()
    await copilot.start() # Note: copilot needs start method defined or simply subscribes in init?
    # Checking copilot.py: it has async start/stop methods. Good.

    # Start WebSocket Data Feed
    global ws_client
    ws_client = BybitWebSocket()

    # Subscribe to 1-minute candles for all symbols
    topics = [f"kline.1.{s}" for s in symbols]
    # Note: connect() runs a loop, so we must run it as a task
    asyncio.create_task(ws_client.connect(topics))

    logger.info("system_online", engine="active", strategies=active_strategies, symbols=symbols)

    # Keep alive
    try:
        # Create an event that waits forever (or until signal)
        stop_event = asyncio.Event()
        
        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
            
        await stop_event.wait()
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Graceful exit already handled by signal handlers mostly, but fallback here
        pass
