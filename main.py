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
from antigravity.profiles import get_current_profile, apply_profile_to_settings

# Import Strategy Classes
from antigravity.strategies.trend_improved import GoldenCrossImproved as TrendFollowingStrategy
from antigravity.strategies.mean_reversion_improved import BollingerRSIImproved as MeanReversionStrategy
from antigravity.strategies.volatility import VolatilityBreakoutStrategy
from antigravity.strategies.scalping import ScalpingStrategy
from antigravity.strategies.bb_squeeze import BBSqueezeStrategy
from antigravity.strategies.grid_improved import GridMasterImproved as GridStrategy
from antigravity.strategies.dynamic_risk_leverage import DynamicRiskLeverageStrategy
from antigravity.strategies.spot_recovery import SpotRecoveryStrategy

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

def is_strategy_enabled(strategy_config, yaml_key, env_names):
    """
    Check if strategy should be enabled.
    Priority:
    1. If ACTIVE_STRATEGIES in .env is not empty, it acts as an exclusive list.
    2. Otherwise, use the 'enabled' flag from strategies.yaml.
    """
    if not strategy_config:
        return False

    active_env = settings.ACTIVE_STRATEGIES

    # If ACTIVE_STRATEGIES is set in .env, it takes precedence as an exclusive filter
    if active_env and (isinstance(active_env, list) and len(active_env) > 0 or isinstance(active_env, str) and len(active_env) > 0):
        if isinstance(active_env, str):
            active_env = [s.strip() for s in active_env.split(",")]

        for name in env_names:
            if name in active_env:
                return True
        return False # Not in the active list

    # Fallback to YAML configuration
    return strategy_config.enabled

async def main():
    # 1. Setup Logging
    configure_logging()
    logger.info("system_startup")

    # 1.5 Load and apply trading profile
    profile = get_current_profile()
    apply_profile_to_settings()
    logger.info("profile_loaded", name=profile.name, is_testnet=profile.is_testnet)

    # 2. Load Configuration
    config = load_strategy_config("strategies.yaml")
    symbols = settings.TRADING_SYMBOLS

    # 3. Initialize Strategies
    
    if is_strategy_enabled(config.trend_following, "trend_following", ["MACD_Trend", "GoldenCross", "TrendFollowing"]):
        strategy_engine.register_strategy(TrendFollowingStrategy(config.trend_following, symbols))
        logger.info("strategy_registered", name="TrendFollowing")

    if is_strategy_enabled(config.mean_reversion, "mean_reversion", ["RSI_Reversion", "BollingerRSI", "MeanReversion"]):
        strategy_engine.register_strategy(MeanReversionStrategy(config.mean_reversion, symbols))
        logger.info("strategy_registered", name="MeanReversion")

    if is_strategy_enabled(config.volatility_breakout, "volatility_breakout", ["ATRBreakout", "VolatilityBreakout"]):
        strategy_engine.register_strategy(VolatilityBreakoutStrategy(config.volatility_breakout, symbols))
        logger.info("strategy_registered", name="VolatilityBreakout")

    if is_strategy_enabled(config.scalping, "scalping", ["StochScalp", "Scalping"]):
        strategy_engine.register_strategy(ScalpingStrategy(config.scalping, symbols))
        logger.info("strategy_registered", name="Scalping")

    if is_strategy_enabled(config.bb_squeeze, "bb_squeeze", ["BBSqueeze"]):
        strategy_engine.register_strategy(BBSqueezeStrategy(config.bb_squeeze, symbols))
        logger.info("strategy_registered", name="BBSqueeze")

    if is_strategy_enabled(config.grid, "grid", ["GridMaster", "Grid"]):
        strategy_engine.register_strategy(GridStrategy(config.grid, symbols))
        logger.info("strategy_registered", name="Grid")

    if is_strategy_enabled(config.dynamic_risk_leverage, "dynamic_risk_leverage", ["DynamicRiskLeverage"]):
        strategy_engine.register_strategy(DynamicRiskLeverageStrategy(config.dynamic_risk_leverage, symbols))
        logger.info("strategy_registered", name="DynamicRiskLeverage")

    # Spot Recovery Strategy (always registered, but only active if in recovery mode logic)
    strategy_engine.register_strategy(SpotRecoveryStrategy(symbols))
    logger.info("strategy_registered", name="SpotRecovery")
    
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
