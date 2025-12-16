from typing import List, Optional
from decimal import Decimal
import pandas as pd
import pandas_ta as ta  # Hummingbot uses pandas_ta usually

from hummingbot.strategy.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.strategy.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig, TripleBarrierConf
from hummingbot.core.data_type.common import TradeType, OrderType
from hummingbot.strategy.strategy_v2.models.executor_actions import ExecutorAction, CreateExecutorAction, StopExecutorAction

class MACDControllerConfig(ControllerConfigBase):
    controller_name: str = "macd_controller"
    candles_connector: str = "bybit_perpetual"
    candles_trading_pair: str = "BTC-USDT"
    interval: str = "1m"
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    leverage: int = 10
    position_size_quote: Decimal = Decimal("100")
    stop_loss: Decimal = Decimal("0.02")
    take_profit: Decimal = Decimal("0.04")
    time_limit: int = 60 * 60 * 24

class MACDController(ControllerBase):
    def __init__(self, config: MACDControllerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

    async def update_processed_data(self):
        df = self.market_data_provider.get_candles_df(
            connector_name=self.config.candles_connector,
            trading_pair=self.config.candles_trading_pair,
            interval=self.config.interval
        )
        if len(df) < self.config.slow_period + self.config.signal_period:
            return

        # Calculate MACD
        macd = ta.macd(close=df["close"], fast=self.config.fast_period, slow=self.config.slow_period, signal=self.config.signal_period)

        # Append columns to df (pandas_ta returns columns like MACD_12_26_9, MACDh_..., MACDs_...)
        # We'll normalize names
        df["macd"] = macd[f"MACD_{self.config.fast_period}_{self.config.slow_period}_{self.config.signal_period}"]
        df["signal"] = macd[f"MACDs_{self.config.fast_period}_{self.config.slow_period}_{self.config.signal_period}"]
        df["hist"] = macd[f"MACDh_{self.config.fast_period}_{self.config.slow_period}_{self.config.signal_period}"]

        self.processed_data = df

    def determine_executor_actions(self) -> List[ExecutorAction]:
        """
        Determine actions based on the processed data.
        """
        if self.processed_data is None or len(self.processed_data) < 2:
            return []

        df = self.processed_data
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # Check if we already have an active executor
        # Simple logic: 1 active trade at a time
        active_executors = self.executors_info
        if len(active_executors) > 0:
            # We could implement logic to close if signal reverses
            return []

        # Signal Logic
        # Buy: MACD Crosses Above Signal
        buy_signal = (prev["macd"] <= prev["signal"]) and (curr["macd"] > curr["signal"])

        # Sell: MACD Crosses Below Signal
        sell_signal = (prev["macd"] >= prev["signal"]) and (curr["macd"] < curr["signal"])

        if buy_signal:
            return [self.create_executor(TradeType.BUY)]
        elif sell_signal:
            return [self.create_executor(TradeType.SELL)]

        return []

    def create_executor(self, trade_type: TradeType) -> CreateExecutorAction:
        return CreateExecutorAction(
            controller_id=self.config.id,
            executor_config=PositionExecutorConfig(
                timestamp=self.market_data_provider.time(),
                connector_name=self.config.candles_connector,
                trading_pair=self.config.candles_trading_pair,
                side=trade_type,
                entry_price=Decimal(self.processed_data.iloc[-1]["close"]), # Approximate, market order uses this for reference or limits
                amount=self.config.position_size_quote / Decimal(self.processed_data.iloc[-1]["close"]), # Quote to Base
                leverage=self.config.leverage,
                triple_barrier_conf=TripleBarrierConf(
                    stop_loss=self.config.stop_loss,
                    take_profit=self.config.take_profit,
                    time_limit=self.config.time_limit
                )
            )
        )
