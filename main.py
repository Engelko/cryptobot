import asyncio
import signal
from antigravity.logging import configure_logging, get_logger
from antigravity.engine import strategy_engine
from antigravity.event import event_bus
from antigravity.copilot import AICopilot
from antigravity.websocket_client import BybitWebSocket
from antigravity.websocket_private import BybitPrivateWebSocket
from antigravity.strategies.config import load_strategy_config
from antigravity.config import settings

# Import Strategy Classes
from antigravity.strategies.trend import TrendFollowingStrategy
from antigravity.strategies.mean_reversion import MeanReversionStrategy
from antigravity.strategies.volatility import VolatilityBreakoutStrategy
from antigravity.strategies.scalping import ScalpingStrategy
from antigravity.strategies.bb_squeeze import BBSqueezeStrategy
from antigravity.strategies.grid import GridStrategy

logger = get_logger("main")

# Global reference to keep the websocket client alive
ws_client = None
ws_task = None
ws_private_client = None
ws_private_task = None

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info("system_shutdown_initiated", signal=signal.name)
    
    if ws_client:
        await ws_client.close()
    if ws_private_client:
        await ws_private_client.close()

    if ws_task and not ws_task.done():
        ws_task.cancel()
    if ws_private_task and not ws_private_task.done():
        ws_private_task.cancel()

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

    # 2. Load Configuration
    config = load_strategy_config("strategies.yaml")
    symbols = settings.TRADING_SYMBOLS

    # 3. Initialize Strategies
    
    if config.trend_following and config.trend_following.enabled:
        strategy_engine.register_strategy(TrendFollowingStrategy(config.trend_following, symbols))
        logger.info("strategy_registered", name="TrendFollowing")

    if config.mean_reversion and config.mean_reversion.enabled:
        strategy_engine.register_strategy(MeanReversionStrategy(config.mean_reversion, symbols))
        logger.info("strategy_registered", name="MeanReversion")

    if config.volatility_breakout and config.volatility_breakout.enabled:
        strategy_engine.register_strategy(VolatilityBreakoutStrategy(config.volatility_breakout, symbols))
        logger.info("strategy_registered", name="VolatilityBreakout")

    if config.scalping and config.scalping.enabled:
        strategy_engine.register_strategy(ScalpingStrategy(config.scalping, symbols))
        logger.info("strategy_registered", name="Scalping")

    if config.bb_squeeze and config.bb_squeeze.enabled:
        strategy_engine.register_strategy(BBSqueezeStrategy(config.bb_squeeze, symbols))
        logger.info("strategy_registered", name="BBSqueeze")

    if config.grid and config.grid.enabled:
        strategy_engine.register_strategy(GridStrategy(config.grid, symbols))
        logger.info("strategy_registered", name="Grid")
    
    # Initialize Engine & Event Bus
    event_bus.start()
    await strategy_engine.start()
    
    # Start AI Copilot
    copilot = AICopilot()
    await copilot.start()

    # 4. Start WebSocket Data Feeds
    global ws_client, ws_task, ws_private_client, ws_private_task

    # Public Stream (Klines)
    ws_client = BybitWebSocket()
    topics = [f"kline.1.{s}" for s in symbols]
    ws_task = asyncio.create_task(ws_client.connect(topics))

    # Private Stream (Orders/Executions) - Required for Grid
    ws_private_client = BybitPrivateWebSocket()
    ws_private_task = asyncio.create_task(ws_private_client.connect())

    def _ws_done_callback(t):
        try:
            t.result()
        except asyncio.CancelledError:
            logger.info("ws_task_cancelled")
        except Exception as e:
            logger.error("ws_task_failed", error=str(e))

    ws_task.add_done_callback(_ws_done_callback)
    ws_private_task.add_done_callback(_ws_done_callback)

    logger.info("system_online", engine="active", symbols=symbols)

    # Log Registered Strategies
    active_names = [name for name, s in strategy_engine.strategies.items() if s.is_active]
    logger.info("active_strategies_list", strategies=active_names)

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
        pass
