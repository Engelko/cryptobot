from typing import List, Optional
from decimal import Decimal
import pandas as pd
import pandas_ta as ta

from hummingbot.strategy.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.strategy.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig, TripleBarrierConf
from hummingbot.core.data_type.common import TradeType, OrderType
from hummingbot.strategy.strategy_v2.models.executor_actions import ExecutorAction, CreateExecutorAction

class RSIControllerConfig(ControllerConfigBase):
    controller_name: str = "rsi_controller"
    candles_connector: str = "bybit_perpetual"
    candles_trading_pair: str = "BTC-USDT"
    interval: str = "1m"
    period: int = 14
    overbought: int = 70
    oversold: int = 30
    leverage: int = 10
    position_size_quote: Decimal = Decimal("100")
    stop_loss: Decimal = Decimal("0.02")
    take_profit: Decimal = Decimal("0.04")
    time_limit: int = 60 * 60 * 24

class RSIController(ControllerBase):
    def __init__(self, config: RSIControllerConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config

    async def update_processed_data(self):
        df = self.market_data_provider.get_candles_df(
            connector_name=self.config.candles_connector,
            trading_pair=self.config.candles_trading_pair,
            interval=self.config.interval
        )
        if len(df) < self.config.period:
            return

        # Calculate RSI
        df["rsi"] = ta.rsi(close=df["close"], length=self.config.period)
        self.processed_data = df

    def determine_executor_actions(self) -> List[ExecutorAction]:
        if self.processed_data is None or len(self.processed_data) < 2:
            return []

        df = self.processed_data
        curr_rsi = df.iloc[-1]["rsi"]

        active_executors = self.executors_info
        if len(active_executors) > 0:
            return []

        # Signal Logic
        # Buy: RSI < Oversold
        if curr_rsi < self.config.oversold:
            return [self.create_executor(TradeType.BUY)]

        # Sell: RSI > Overbought
        if curr_rsi > self.config.overbought:
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
                entry_price=Decimal(self.processed_data.iloc[-1]["close"]),
                amount=self.config.position_size_quote / Decimal(self.processed_data.iloc[-1]["close"]),
                leverage=self.config.leverage,
                triple_barrier_conf=TripleBarrierConf(
                    stop_loss=self.config.stop_loss,
                    take_profit=self.config.take_profit,
                    time_limit=self.config.time_limit
                )
            )
        )
