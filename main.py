import asyncio
import signal
from antigravity.logging import configure_logging, get_logger
from antigravity.engine import strategy_engine
from antigravity.event import event_bus
from antigravity.strategies.macd import MACDStrategy
from antigravity.strategies.rsi import RSIStrategy
from antigravity.copilot import AICopilot
from antigravity.execution import execution_manager

logger = get_logger("main")

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info("system_shutdown_initiated", signal=signal.name)
    
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
    # MACD Params: 12, 26, 9
    macd = MACDStrategy(name="MACD_Trend", symbols=["BTCUSDT"])
    strategy_engine.register_strategy(macd)
    
    # RSI Params: 14, 70, 30
    rsi = RSIStrategy(name="RSI_Reversion", symbols=["BTCUSDT"])
    strategy_engine.register_strategy(rsi)
    
    # Initialize Engine & Event Bus
    event_bus.start()
    await strategy_engine.start()
    
    # Start AI Copilot
    copilot = AICopilot()
    await copilot.start() # Note: copilot needs start method defined or simply subscribes in init?
    # Checking copilot.py: it has async start/stop methods. Good.

    logger.info("system_online", engine="active", strategies=["MACD_Trend", "RSI_Reversion"])

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
