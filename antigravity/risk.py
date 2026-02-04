import time
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any
from antigravity.config import settings
from antigravity.strategy import Signal, SignalType
from antigravity.regime_detector import MarketRegime, market_regime_detector
from antigravity.logging import get_logger
from antigravity.client import BybitClient
from antigravity.database import db
from antigravity.utils import safe_float
from antigravity.event import event_bus, TradeClosedEvent, OrderUpdateEvent, KlineEvent, on_event
from antigravity.metrics import metrics
from antigravity.telegram_alerts import telegram_alerts

logger = get_logger("risk_manager")

# Minimum order cost in USDT (approximate)
MIN_ORDER_COST = 10.0

class TradingMode(Enum):
    NORMAL = "NORMAL"
    RECOVERY = "RECOVERY"  # Spot only, reduced size
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Full stop

class RiskManager:
    def __init__(self):
        self.initial_deposit = settings.INITIAL_DEPOSIT
        self.max_daily_loss = settings.MAX_DAILY_LOSS
        self.current_daily_loss = 0.0
        self.last_reset_date = None
        self.trading_mode = TradingMode.NORMAL
        self.consecutive_loss_days = 0

        # Local position tracking for cascade stops
        self.active_positions: Dict[str, Dict[str, Any]] = {}

        # Load persisted state
        state = db.get_risk_state()
        if state:
            if hasattr(state, "daily_loss"):
                self.current_daily_loss = state.daily_loss
                self.last_reset_date = state.last_reset_date
                self.consecutive_loss_days = getattr(state, "consecutive_loss_days", 0)
            else:
                self.current_daily_loss = state.get("daily_loss", 0.0)
                self.last_reset_date = state.get("last_reset_date")
                self.consecutive_loss_days = state.get("consecutive_loss_days", 0)

        # Subscribe to events
        event_bus.subscribe(TradeClosedEvent, self._handle_trade_closed)
        event_bus.subscribe(OrderUpdateEvent, self._handle_order_update)
        event_bus.subscribe(KlineEvent, self._handle_kline)

    def _get_current_utc_date(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_reset(self):
        current_date = self._get_current_utc_date()
        if self.last_reset_date != current_date:
            logger.info("risk_daily_reset", old_date=self.last_reset_date, new_date=current_date, previous_loss=self.current_daily_loss)

            # Check if previous day was a loss day (hit limit)
            if self.current_daily_loss >= self.max_daily_loss:
                self.consecutive_loss_days += 1
            else:
                self.consecutive_loss_days = 0

            self.current_daily_loss = 0.0
            self.last_reset_date = current_date
            db.update_risk_state(self.current_daily_loss, self.last_reset_date, self.consecutive_loss_days)

    async def _handle_trade_closed(self, event: TradeClosedEvent):
        if event.pnl < 0:
            self._check_reset()
            self.current_daily_loss += abs(event.pnl)
            db.update_risk_state(self.current_daily_loss, self.last_reset_date, self.consecutive_loss_days)
            logger.info("risk_loss_updated", added_loss=abs(event.pnl), total_daily_loss=self.current_daily_loss)

    async def _handle_order_update(self, event: OrderUpdateEvent):
        """Track positions for local monitoring."""
        if event.order_status == "Filled":
            symbol = event.symbol
            side = event.side
            qty = event.qty
            price = event.price

            if symbol not in self.active_positions:
                self.active_positions[symbol] = {
                    "side": side,
                    "entry_price": price,
                    "qty": qty,
                    "max_price_seen": price if side == "Buy" else -1.0,
                    "min_price_seen": price if side == "Sell" else 999999.0,
                    "trailing_active": False
                }
            else:
                # Update existing (Average entry logic could be added)
                pos = self.active_positions[symbol]
                if side == pos["side"]:
                    # Increase position
                    new_qty = pos["qty"] + qty
                    pos["entry_price"] = (pos["entry_price"] * pos["qty"] + price * qty) / new_qty
                    pos["qty"] = new_qty
                else:
                    # Decrease or close
                    if qty >= pos["qty"]:
                        del self.active_positions[symbol]
                    else:
                        pos["qty"] -= qty

    async def _handle_kline(self, event: KlineEvent):
        """Local monitoring of SL/TS."""
        symbol = event.symbol
        if symbol not in self.active_positions:
            return

        pos = self.active_positions[symbol]
        current_price = event.close
        side = pos["side"]

        # Level 1: Hard Stop Loss (-2%)
        if side == "Buy":
            sl_price = pos["entry_price"] * (1 - settings.STOP_LOSS_PCT)
            if current_price <= sl_price:
                logger.warning("local_sl_triggered", symbol=symbol, price=current_price, sl=sl_price)
                await self._emergency_close(symbol)
                return

            # Update max price for trailing stop
            if current_price > pos["max_price_seen"]:
                pos["max_price_seen"] = current_price

            # Trailing Stop Trigger (+1.5% profit)
            profit_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
            if profit_pct >= settings.TRAILING_STOP_TRIGGER:
                pos["trailing_active"] = True

            if pos["trailing_active"]:
                # Trailing SL: 1.5% from max seen price
                ts_sl = pos["max_price_seen"] * (1 - settings.TRAILING_STOP_TRIGGER)
                if current_price <= ts_sl:
                    logger.warning("local_ts_triggered", symbol=symbol, price=current_price, ts_sl=ts_sl)
                    await self._emergency_close(symbol)

        elif side == "Sell":
            sl_price = pos["entry_price"] * (1 + settings.STOP_LOSS_PCT)
            if current_price >= sl_price:
                logger.warning("local_sl_triggered", symbol=symbol, price=current_price, sl=sl_price)
                await self._emergency_close(symbol)
                return

            if current_price < pos["min_price_seen"]:
                pos["min_price_seen"] = current_price

            profit_pct = (pos["entry_price"] - current_price) / pos["entry_price"]
            if profit_pct >= settings.TRAILING_STOP_TRIGGER:
                pos["trailing_active"] = True

            if pos["trailing_active"]:
                ts_sl = pos["min_price_seen"] * (1 + settings.TRAILING_STOP_TRIGGER)
                if current_price >= ts_sl:
                    logger.warning("local_ts_triggered", symbol=symbol, price=current_price, ts_sl=ts_sl)
                    await self._emergency_close(symbol)

    async def _emergency_close(self, symbol: str):
        """Force close position via Market order."""
        logger.info("emergency_close_executing", symbol=symbol)
        from antigravity.execution import execution_manager
        pos = self.active_positions.get(symbol)
        if not pos: return

        side = "Sell" if pos["side"] == "Buy" else "Buy"
        signal = Signal(
            symbol=symbol,
            type=SignalType.SELL if side == "Sell" else SignalType.BUY,
            price=0.0, # Market
            quantity=pos["qty"],
            reason="LOCAL_CASCADE_STOP"
        )
        await execution_manager.execute(signal, "RiskManager_Emergency")
        if symbol in self.active_positions:
            del self.active_positions[symbol]

    async def get_equity(self) -> float:
        balance = await self._get_balance()
        unrealized_pnl = 0.0
        logger.debug("calculating_equity", balance=balance)
        if not settings.SIMULATION_MODE:
            client = BybitClient()
            try:
                positions = await client.get_positions(category="linear")
                for p in positions:
                    unrealized_pnl += safe_float(p.get("unrealisedPnl", 0))
            except Exception as e:
                logger.error("equity_calc_error", error=str(e))
            finally:
                await client.close()
        return balance + unrealized_pnl

    async def _get_balance(self) -> float:
        if settings.SIMULATION_MODE:
            from antigravity.execution import execution_manager
            return execution_manager.paper_broker.balance
        
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            if "totalWalletBalance" in balance_data:
                return safe_float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        return safe_float(c.get("walletBalance", 0.0))
        except Exception as e:
            logger.error("balance_fetch_failed", error=str(e))
        finally:
            await client.close()
        return 0.0

    async def update_trading_mode(self):
        """Update trading mode based on equity. Uses caching to prevent rate limits."""
        # Check cache (1 minute)
        now = time.time()
        if hasattr(self, '_last_mode_check') and now - self._last_mode_check < 60:
            return

        equity = await self.get_equity()

        # Auto-initialize initial_deposit if it's 0.0
        if self.initial_deposit <= 0:
            self.initial_deposit = equity
            logger.info("risk_auto_init_deposit", amount=self.initial_deposit)

        equity_ratio = equity / self.initial_deposit if self.initial_deposit > 0 else 1.0

        if equity_ratio < settings.EMERGENCY_THRESHOLD:
            self.trading_mode = TradingMode.EMERGENCY_STOP
        elif equity_ratio < 0.80 or self.consecutive_loss_days >= 2:
            # Switch to Spot Recovery if <80% or 2 losing days
            self.trading_mode = TradingMode.RECOVERY
        elif self.trading_mode == TradingMode.RECOVERY and equity_ratio < 0.85:
            # Stay in recovery mode until 85% reached
            self.trading_mode = TradingMode.RECOVERY
        else:
            self.trading_mode = TradingMode.NORMAL

        self._last_mode_check = now
        logger.info("trading_mode_check",
                    equity=round(equity, 2),
                    initial_deposit=self.initial_deposit,
                    ratio=f"{equity_ratio:.2%}",
                    mode=self.trading_mode.value,
                    consecutive_losses=self.consecutive_loss_days)

    async def check_signal(self, signal: Signal) -> tuple[bool, str]:
        self._check_reset()

        # Only update trading mode if it's not already in EMERGENCY_STOP
        # (or periodically as handled by update_trading_mode cache)
        if self.trading_mode != TradingMode.EMERGENCY_STOP:
            await self.update_trading_mode()

        if self.trading_mode == TradingMode.EMERGENCY_STOP:
            logger.critical("risk_block", reason="EMERGENCY_STOP", equity_ratio="<50%")
            await telegram_alerts.send_message("🚨 <b>EMERGENCY STOP</b>\nEquity dropped below 50% threshold.")
            # In emergency stop, we might want to close all positions too
            await self._close_all_positions()
            return False, "EMERGENCY_STOP: Equity < 50%"

        if self.current_daily_loss >= settings.MAX_DAILY_LOSS:
            logger.warning("risk_block", reason="daily_loss_limit_exceeded",
                           current_loss=self.current_daily_loss, limit=settings.MAX_DAILY_LOSS)
            await telegram_alerts.send_message(f"⚠️ <b>DAILY LOSS LIMIT REACHED</b>\nCurrent: -${self.current_daily_loss:.2f}")
            # Close all positions on daily limit hit
            await self._close_all_positions()
            return False, f"Daily loss limit reached (${self.current_daily_loss:.2f})"

        if await self._is_reduce_only(signal):
            return True, "Reduce-only order accepted"

        balance = await self._get_balance()
        leverage = signal.leverage if signal.leverage and signal.leverage > 0 else 1.0
        if leverage > settings.MAX_LEVERAGE:
            leverage = settings.MAX_LEVERAGE
            signal.leverage = leverage

        daily_loss_left = max(0, settings.MAX_DAILY_LOSS - self.current_daily_loss)

        # Use risk percentage from signal if provided, otherwise default to 2%
        risk_per_trade = getattr(signal, 'risk_percentage', 0.02)
        if risk_per_trade is None or risk_per_trade <= 0:
            risk_per_trade = 0.02

        size_by_pct = balance * risk_per_trade
        size_by_abs = settings.MAX_POSITION_SIZE

        # Calculate size based on remaining daily loss budget
        # Formula: Position Size = Max Loss / Stop Loss Percentage
        risk_size = daily_loss_left / settings.STOP_LOSS_PCT if settings.STOP_LOSS_PCT > 0 else size_by_abs

        target_size = min(size_by_pct, size_by_abs, risk_size)

        # Check for High Volatility
        regime_data = market_regime_detector.regimes.get(signal.symbol)
        is_volatile = regime_data and regime_data.regime == MarketRegime.VOLATILE

        if self.trading_mode == TradingMode.RECOVERY or is_volatile:
            # Force Spot and reduce size in recovery or high volatility
            target_size = min(target_size, balance * 0.20)
            signal.category = "spot"
            signal.leverage = 1.0 # No leverage on spot
            reason = "VOLATILE_REGIME" if is_volatile else "RECOVERY_MODE"
            logger.info("spot_only_mode_active", reason=reason, symbol=signal.symbol, target_size=target_size)

        if signal.price and signal.price > 0:
            target_qty = target_size / signal.price
            if target_size < MIN_ORDER_COST:
                return False, f"Size too small: ${target_size:.2f} < ${MIN_ORDER_COST}"
            signal.quantity = target_qty

        signal.stop_loss = signal.price * (1 - settings.STOP_LOSS_PCT) if signal.type == SignalType.BUY else signal.price * (1 + settings.STOP_LOSS_PCT)
        return True, signal.reason

    async def _close_all_positions(self):
        symbols = list(self.active_positions.keys())
        for s in symbols:
            await self._emergency_close(s)

    async def _is_reduce_only(self, signal: Signal) -> bool:
        if settings.SIMULATION_MODE:
             from antigravity.execution import execution_manager
             pos = execution_manager.paper_broker.positions.get(signal.symbol)
             if pos and pos["quantity"] > 0:
                 if signal.type == SignalType.SELL: return True
             return False

        client = BybitClient()
        try:
            category = getattr(signal, 'category', 'linear')
            if category == 'spot':
                # For spot, check if we have balance of the base coin
                coin = signal.symbol.replace("USDT", "")
                balance_data = await client.get_wallet_balance(coin=coin)

                coin_qty = 0.0
                if "coin" in balance_data:
                    for c in balance_data["coin"]:
                        if c.get("coin") == coin:
                            coin_qty = safe_float(c.get("walletBalance", 0))
                            break

                if coin_qty > 0 and signal.type == SignalType.SELL:
                    return True
            else:
                positions = await client.get_positions(category="linear", symbol=signal.symbol)
                for p in positions:
                    size = safe_float(p.get("size", 0))
                    side = p.get("side")
                    if size > 0:
                        if side == "Buy" and signal.type == SignalType.SELL: return True
                        if side == "Sell" and signal.type == SignalType.BUY: return True
        except Exception as e:
            logger.error("reduce_only_check_error", error=str(e))
        finally:
            await client.close()
        return False
