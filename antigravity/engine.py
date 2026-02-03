import asyncio
from typing import Dict, List
from antigravity.logging import get_logger
from antigravity.event import event_bus, MarketDataEvent, KlineEvent, OrderUpdateEvent, on_event, SentimentEvent, TradeClosedEvent
from antigravity.strategy import AbstractStrategy, Signal
from antigravity.risk import RiskManager
from antigravity.database import db
from antigravity.execution import execution_manager
from antigravity.ml_engine import ml_engine
from antigravity.client import BybitClient
from antigravity.regime_detector import market_regime_detector
from antigravity.router import strategy_router
from antigravity.onchain_analyzer import onchain_analyzer
from antigravity.performance_guard import performance_guard
import pandas as pd

logger = get_logger("strategy_engine")

class StrategyEngine:
    def __init__(self):
        self.strategies: Dict[str, AbstractStrategy] = {}
        self._running = False
        self.risk_manager = RiskManager()
        self.ml_engine = ml_engine
        self.latest_predictions: Dict[str, Dict] = {}

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

    async def _onchain_update_loop(self):
        """Background loop to update on-chain metrics."""
        while self._running:
            try:
                await onchain_analyzer.fetch_onchain_data()
                await onchain_analyzer.check_whale_activity()
            except Exception as e:
                logger.error("onchain_loop_error", error=str(e))
            await asyncio.sleep(3600) # Update hourly

    async def start(self):
        self._running = True
        logger.info("strategy_engine_started")

        # Start on-chain loop
        asyncio.create_task(self._onchain_update_loop())

        # Start all strategies
        for name, strategy in self.strategies.items():
            try:
                await strategy.start()
                logger.info("strategy_started", strategy=name)
            except Exception as e:
                logger.error("strategy_start_failed", strategy=name, error=str(e))

        # Perform Warmup
        await self._warmup_strategies()

        if self.ml_engine.enabled:
             logger.info("ml_engine_active")
        
        # Subscribe to Events
        event_bus.subscribe(MarketDataEvent, self._handle_market_data)
        event_bus.subscribe(KlineEvent, self._handle_market_data)
        event_bus.subscribe(OrderUpdateEvent, self._handle_order_update)
        event_bus.subscribe(SentimentEvent, self._handle_sentiment)
        event_bus.subscribe(TradeClosedEvent, self._handle_trade_closed)

    async def _handle_trade_closed(self, event: TradeClosedEvent):
        await performance_guard.check_performance(event.strategy)

    async def stop(self):
        self._running = False

        # Stop all strategies
        for name, strategy in self.strategies.items():
            try:
                await strategy.stop()
                logger.info("strategy_stopped", strategy=name)
            except Exception as e:
                logger.error("strategy_stop_failed", strategy=name, error=str(e))

        logger.info("strategy_engine_stopped")

    async def _handle_market_data(self, event: MarketDataEvent):
        if not self._running:
            return

        # Persist Klines, Update Market Regime & AI Prediction
        if isinstance(event, KlineEvent):
            db.save_kline(event.symbol, event.interval, event.open, event.high, event.low, event.close, event.volume, event.timestamp)

            try:
                 from sqlalchemy import text
                 # Fetch 100 candles for both Regime Detection and AI Agent
                 query = text("SELECT * FROM klines WHERE symbol=:symbol ORDER BY ts DESC LIMIT 100")
                 recent_klines_df = pd.read_sql(query, db.engine, params={"symbol": event.symbol})

                 if not recent_klines_df.empty:
                     recent_klines = recent_klines_df.iloc[::-1].to_dict('records')

                     # 1. Update Regime
                     market_regime_detector.analyze(event.symbol, recent_klines)

                     # 2. AI Prediction (LightGBM)
                     if self.ml_engine.enabled:
                         prediction = await self.ml_engine.predict_price_movement(event.symbol, recent_klines)
                         if prediction:
                             event.prediction = prediction
                             self.latest_predictions[event.symbol] = prediction
                             db.save_prediction(
                                 symbol=event.symbol,
                                 prediction_value=1.0 if prediction.get("direction") == "UP" else 0.0,
                                 confidence=prediction.get("confidence", 0.0),
                                 features={"regime": market_regime_detector.regimes.get(event.symbol).regime.value if event.symbol in market_regime_detector.regimes else "None"}
                             )
            except Exception as e:
                logger.error("market_analysis_failed", symbol=event.symbol, error=str(e))

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

    async def _handle_order_update(self, event: OrderUpdateEvent):
        """Route order updates (fills) to strategies."""
        if not self._running:
            return

        for name, strategy in self.strategies.items():
            if not strategy.is_active:
                continue

            # Optimization: Only send if symbol matches?
            # Strategy checks symbol internally usually, but we can filter here.
            if event.symbol in strategy.symbols:
                try:
                    await strategy.on_order_update(event)
                except Exception as e:
                    logger.error("strategy_order_update_failed", strategy=name, error=str(e))

    async def _handle_sentiment(self, event: SentimentEvent):
        db.save_sentiment("BTCUSDT", event.score, event.reasoning, event.model)

    async def _handle_signal(self, signal: Signal, strategy_name: str):
        """
        Process a signal generated by a strategy. 
        """
        # -1. Performance Guard Check
        if performance_guard.is_disabled(strategy_name):
            return

        # 0. Strategy Router Check (Regime Filter)
        regime_data = market_regime_detector.regimes.get(signal.symbol)
        if not strategy_router.check_signal(signal, strategy_name, regime_data):
            logger.info("signal_rejected_by_router", strategy=strategy_name, symbol=signal.symbol, regime=regime_data.regime.value if regime_data else "None")
             # Save rejected signal
            db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price,
                           f"[REJECTED: Market Regime] {signal.reason}")
            return

        # 1. AI Agent Filter
        if self.ml_engine.enabled:
            pred = self.latest_predictions.get(signal.symbol)
            if pred:
                direction = pred.get("direction")
                confidence = pred.get("confidence", 0.0)

                # Filter: Confidence > 0.6 and direction must match signal
                if confidence < 0.6:
                    logger.info("signal_rejected_by_ai", symbol=signal.symbol, reason="low_confidence", conf=confidence)
                    db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price, f"[REJECTED: AI Low Conf] {confidence:.2f}")
                    return

                if (signal.type == SignalType.BUY and direction != "UP") or \
                   (signal.type == SignalType.SELL and direction != "DOWN"):
                    logger.info("signal_rejected_by_ai", symbol=signal.symbol, reason="direction_mismatch", pred=direction)
                    db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price, f"[REJECTED: AI Direction] {direction}")
                    return

        # 2. On-chain Filter
        if not onchain_analyzer.is_whale_safe():
            logger.info("signal_rejected_by_onchain", symbol=signal.symbol, reason="whale_activity")
            db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price, "[REJECTED: Whale Activity]")
            return

        onchain_score = onchain_analyzer.get_score()
        if (signal.type == SignalType.BUY and onchain_score < 0.4) or \
           (signal.type == SignalType.SELL and onchain_score > 0.6):
            logger.info("signal_rejected_by_onchain", symbol=signal.symbol, reason="score_mismatch", score=onchain_score)
            db.save_signal(strategy_name, signal.symbol, signal.type.value, signal.price, f"[REJECTED: On-chain Score {onchain_score:.2f}]")
            return

        # 3. Risk Check
        if not await self.risk_manager.check_signal(signal):
            logger.warning("signal_rejected_by_risk", strategy=strategy_name, symbol=signal.symbol, 
                         leverage=signal.leverage, risk_percentage=signal.risk_percentage)
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
