import os
import yaml
from decimal import Decimal
from typing import Dict, List, Set

from hummingbot.core.data_type.common import PositionMode
from hummingbot.strategy.strategy_v2.strategy_v2 import StrategyV2, StrategyV2Config
from hummingbot.strategy.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig
from hummingbot.client.config.config_helpers import ClientConfigAdapter

# Import custom controllers
from controllers.macd_controller import MACDController, MACDControllerConfig
from controllers.rsi_controller import RSIController, RSIControllerConfig
from controllers.ai_copilot import AICopilot, AICopilotConfig

def load_config(file_path: str) -> Dict:
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def get_strategy_config() -> StrategyV2Config:
    # Load configuration from YAML
    # We assume /conf is mounted to the container's /conf
    config_path = "/conf/antigravity_config.yml"

    # Fallback for local testing if path doesn't exist
    if not os.path.exists(config_path):
        config_path = "conf/antigravity_config.yml"

    try:
        app_config = load_config(config_path)
    except Exception as e:
        print(f"Error loading config from {config_path}: {e}")
        # Return a minimal default or raise
        raise e

    # Parse Parameters
    params = app_config.get("parameters", {})
    leverage = params.get("leverage", 10)
    pos_size = Decimal(str(params.get("position_size_usdt", 100)))
    stop_loss = Decimal(str(params.get("stop_loss_pct", 0.02)))
    take_profit = Decimal(str(params.get("take_profit_pct", 0.04)))
    time_limit = params.get("time_limit", 86400)

    markets = app_config.get("markets", {}).get("bybit_perpetual", ["BTC-USDT"])
    trading_pair = markets[0] # Simplification for single pair per controller demo

    # 1. MACD Config
    macd_config = MACDControllerConfig(
        id="macd_controller",
        candles_connector="bybit_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        leverage=leverage,
        position_size_quote=pos_size,
        stop_loss=stop_loss,
        take_profit=take_profit,
        time_limit=time_limit
    )

    # 2. RSI Config
    rsi_config = RSIControllerConfig(
        id="rsi_controller",
        candles_connector="bybit_perpetual",
        candles_trading_pair=trading_pair,
        interval="1m",
        leverage=leverage,
        position_size_quote=pos_size,
        stop_loss=stop_loss,
        take_profit=take_profit,
        time_limit=time_limit
    )

    # 3. AI Config
    ai_config = AICopilotConfig(
        id="ai_copilot",
        candles_connector="bybit_perpetual",
        candles_trading_pair=trading_pair,
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_model=app_config.get("ai", {}).get("model", "deepseek-chat")
    )

    # Filter active controllers
    active_list = app_config.get("active_controllers", [])
    controllers_to_use = []

    if "macd_controller" in active_list:
        controllers_to_use.append(macd_config)
    if "rsi_controller" in active_list:
        controllers_to_use.append(rsi_config)
    if "ai_copilot" in active_list:
        controllers_to_use.append(ai_config)

    # Strategy Config
    config = StrategyV2Config(
        markets={"bybit_perpetual": set(markets)},
        candles_config=[
            {"connector": "bybit_perpetual", "trading_pair": p, "interval": "1m"} for p in markets
        ],
        controllers_config=controllers_to_use
    )
    return config

def start(hummingbot):
    """
    Entry point for the script.
    """
    try:
        strategy_config = get_strategy_config()

        # Instantiate Controllers manually to ensure class usage
        controllers_map = {}
        for conf in strategy_config.controllers_config:
            if isinstance(conf, MACDControllerConfig):
                c = MACDController(config=conf, market_data_provider=hummingbot.market_data_provider, executors_handler=hummingbot.executors_handler)
                controllers_map[conf.id] = c
            elif isinstance(conf, RSIControllerConfig):
                c = RSIController(config=conf, market_data_provider=hummingbot.market_data_provider, executors_handler=hummingbot.executors_handler)
                controllers_map[conf.id] = c
            elif isinstance(conf, AICopilotConfig):
                c = AICopilot(config=conf, market_data_provider=hummingbot.market_data_provider, executors_handler=hummingbot.executors_handler)
                controllers_map[conf.id] = c

        # Create the strategy
        strategy = StrategyV2(config=strategy_config, market_data_provider=hummingbot.market_data_provider, executors_handler=hummingbot.executors_handler)

        # Inject custom controllers
        strategy.controllers = controllers_map

        hummingbot.strategy = strategy

    except Exception as e:
        hummingbot.notify(f"Failed to start Antigravity: {e}")
        raise e
