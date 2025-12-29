import asyncio
from typing import Dict, List
from antigravity.logging import get_logger
from antigravity.event import event_bus, MarketDataEvent, KlineEvent, on_event, SentimentEvent
from antigravity.strategy import AbstractStrategy, Signal
from antigravity.risk import RiskManager
from antigravity.database import db
from antigravity.execution import execution_manager
from antigravity.ml_engine import ml_engine
from antigravity.client import BybitClient
import pandas as pd

logger = get_logger("strategy_engine")

class StrategyEngine:
    def __init__(self):
        self.strategies: Dict[str, AbstractStrategy] = {}
        self._running = False
        self.risk_manager = RiskManager()
        self.ml_engine = ml_engine

    def register_strategy(self, strategy: AbstractStrategy):
        self.strategies[strategy.name] = strategy
        logger.info("strategy_registered", name=strategy.name, symbols=strategy.symbols)

    async def _warmup_strategies(self):
        """
        Load historical klines from the database and feed them to strategies
        to pre-calculate indicators (RSI, MACD) so they are ready to trade immediately.
        """
        logger.info("warmup_started")
        try:
            # Gather all unique symbols from registered strategies
            all_symbols = set()
            for strategy in self.strategies.values():
                all_symbols.update(strategy.symbols)

            # Create a DB engine for pandas (if not already available in db, but db instance uses sqlalchemy session)
            # We can use db.engine which is exposed in Database class

            # Create a DB engine for pandas
            client = None

            for symbol in all_symbols:
                # 1. Try Loading from DB
                query = f"SELECT * FROM klines WHERE symbol='{symbol}' ORDER BY ts DESC LIMIT 300"
                df = pd.read_sql(query, db.engine)

                # 2. If Empty/Insufficient, Fetch from API
                if df.empty or len(df) < 50:
                    logger.info("warmup_fetching_api", symbol=symbol)
                    if not client:
                        client = BybitClient()

                    # Fetch 200 candles (API limit usually)
                    klines = await client.get_kline(symbol=symbol, interval="1", limit=200)
                    if klines:
                        # Save to DB
                        for k in klines:
                            # Kline: [startTime, open, high, low, close, volume, turnover]
                            # Bybit returns NEWEST first, so we reverse later or insert as is
                            ts = int(k[0])
                            o = float(k[1])
                            h = float(k[2])
                            l = float(k[3])
                            c = float(k[4])
                            v = float(k[5])
                            db.save_kline(symbol, "1", o, h, l, c, v, ts)

                        # Reload from DB to ensure consistency and correct sorting
                        df = pd.read_sql(query, db.engine)

                if df.empty:
                    logger.warning("warmup_no_data_after_fetch", symbol=symbol)
                    continue

                # Sort back to ascending (oldest first)
                df = df.sort_values("ts")

                logger.info("warmup_symbol", symbol=symbol, candles=len(df))

                # Feed to strategies
                for _, row in df.iterrows():
                    event = KlineEvent(
                        symbol=symbol,
                        interval=row["interval"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        timestamp=row["ts"]
                    )

                    # Feed to ALL strategies that watch this symbol
                    for strategy in self.strategies.values():
                        if symbol in strategy.symbols and strategy.is_active:
                            # We call on_market_data but normally we don't want to trigger TRADES on historical data
                            # during warmup. However, strategies usually return a Signal object.
                            # We can simply IGNORE the returned signal during warmup.
                            await strategy.on_market_data(event)

            if client:
                await client.close()

        except Exception as e:
            logger.error("warmup_failed", error=str(e))

        logger.info("warmup_complete")

    async def start(self):
        self._running = True
        logger.info("strategy_engine_started")

        # Perform Warmup
        await self._warmup_strategies()

        if self.ml_engine.enabled:
             logger.info("ml_engine_active")
        
        # Subscribe to Events
        event_bus.subscribe(MarketDataEvent, self._handle_market_data)
        event_bus.subscribe(KlineEvent, self._handle_market_data)
        event_bus.subscribe(SentimentEvent, self._handle_sentiment)

    async def stop(self):
        self._running = False
        logger.info("strategy_engine_stopped")

    async def _handle_market_data(self, event: MarketDataEvent):
        if not self._running:
            return

        # Persist Klines
        if isinstance(event, KlineEvent):
            db.save_kline(event.symbol, event.interval, event.open, event.high, event.low, event.close, event.volume, event.timestamp)
            
            # Future: ML Prediction Hook here
            # prediction = await self.ml_engine.predict_price_movement(event.symbol, {"close": event.close})

        # Forward to all strategies
        for name, strategy in self.strategies.items():
            if not strategy.is_active:
                continue
                
            try:
                signal = await strategy.on_market_data(event)
                if signal:
                    await self._handle_signal(signal, strategy.name)
            except Exception as e:
                logger.error("strategy_error", strategy=name, error=str(e))

    async def _handle_sentiment(self, event: SentimentEvent):
        db.save_sentiment("BTCUSDT", event.score, event.reasoning, event.model)

    async def _handle_signal(self, signal: Signal, strategy_name: str):
        """
        Process a signal generated by a strategy. 
        """
        # 1. Risk Check
        if not self.risk_manager.check_signal(signal):
            logger.info("signal_rejected_by_risk", strategy=strategy_name, symbol=signal.symbol)
            # Save rejected signal to DB for visibility in Dashboard
            db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price,
                           f"[REJECTED: Risk Limit] {signal.reason}")
            return

        logger.info("signal_accepted", 
                    strategy=strategy_name, 
                    type=signal.type.value, 
                    symbol=signal.symbol, 
                    price=signal.price)
        
        # 2. Persist Signal
        db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price, signal.reason)

        # 3. Execute Signal
        await execution_manager.execute(signal, strategy_name)

# Global Engine Instance
strategy_engine = StrategyEngine()
