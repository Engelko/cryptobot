import time
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
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

MIN_ORDER_COST = 10.0
BLACKLISTED_SYMBOLS = ["XRPUSDT"]  # Symbols with systematic losses

class TradingMode(Enum):
    NORMAL = "NORMAL"
    RECOVERY = "RECOVERY"  # Spot only, reduced size
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Full stop

CORRELATION_GROUPS = {
    "high": [
        ("BTCUSDT", "ETHUSDT"),
        ("BTCUSDT", "BNBUSDT"),
        ("ETHUSDT", "BNBUSDT"),
        ("SOLUSDT", "ETHUSDT"),
    ],
    "medium": [
        ("BTCUSDT", "SOLUSDT"),
        ("ETHUSDT", "ADAUSDT"),
    ]
}

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
        self.position_entry_time: Dict[str, float] = {}
        self.trailing_activation_time: Dict[str, float] = {}
        self.pending_quality: Dict[str, int] = {}
        self._last_loss_time: float = 0.0

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
        self._check_reset()
        self.current_daily_loss -= event.pnl
        db.update_risk_state(self.current_daily_loss, self.last_reset_date, self.consecutive_loss_days)
        logger.info("risk_pnl_updated", pnl=event.pnl, total_daily_loss=self.current_daily_loss)
        
        # Track last loss time for cooldown
        if event.pnl < 0:
            self._last_loss_time = time.time()
            logger.info("loss_recorded", pnl=event.pnl, cooldown_start="now")

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
                    "trailing_active": False,
                    "quality_score": self.pending_quality.pop(symbol, 2)
                }
                self.position_entry_time[symbol] = time.time()
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
                        self.position_entry_time.pop(symbol, None)
                        self.trailing_activation_time.pop(symbol, None)
                    else:
                        pos["qty"] -= qty

    async def _handle_kline(self, event: KlineEvent):
        """
        Local monitoring of SL/TS with improved logic.
        
        KEY FIXES:
        1. MIN_HOLD_TIME: Don't trigger SL in first 60 seconds
        2. TAKE_PROFIT: Auto-close at target profit
        3. PROFIT_CHECK: Don't trigger SL if position is profitable
        4. MAX_LOSS_PER_EXIT: Alert if exit loss exceeds threshold
        """
        symbol = event.symbol
        if symbol not in self.active_positions:
            return

        pos = self.active_positions[symbol]
        current_price = event.close
        pos["last_price"] = current_price
        side = pos["side"]
        entry_price = pos["entry_price"]
        qty = pos["qty"]
        entry_time = self.position_entry_time.get(symbol, time.time())
        hold_time = time.time() - entry_time

        # Calculate unrealized PnL
        if side == "Buy":
            unrealized_pnl = (current_price - entry_price) * qty
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        else:
            unrealized_pnl = (entry_price - current_price) * qty
            pnl_pct = (entry_price - current_price) / entry_price if entry_price > 0 else 0

        # FIX 1: Minimum hold time check
        min_hold_time = getattr(settings, 'MIN_HOLD_TIME', 60)
        if hold_time < min_hold_time:
            return

        # FIX 2: Take Profit check (before SL)
        take_profit_pct = getattr(settings, 'TAKE_PROFIT_PCT', 0.03)
        if pnl_pct >= take_profit_pct:
            logger.info("take_profit_triggered", symbol=symbol, pnl_pct=f"{pnl_pct:.2%}", pnl=unrealized_pnl)
            await self._profit_close(symbol, reason="TAKE_PROFIT")
            return

        # FIX 3: Don't trigger SL if in profit
        if unrealized_pnl > 0:
            return

        # === STOP LOSS LOGIC ===
        if side == "Buy":
            sl_price = entry_price * (1 - settings.STOP_LOSS_PCT)
            if current_price <= sl_price:
                potential_loss = abs(unrealized_pnl)
                max_loss_per_exit = getattr(settings, 'MAX_LOSS_PER_EXIT', 5.0)
                
                if potential_loss > max_loss_per_exit:
                    logger.warning("exit_loss_exceeds_max", symbol=symbol, 
                                  loss=potential_loss, max_allowed=max_loss_per_exit)
                    await telegram_alerts.send_message(
                        f"⚠️ <b>Large Exit Loss</b>\n{symbol}: ${potential_loss:.2f} > MAX ${max_loss_per_exit}"
                    )
                
                logger.warning("local_sl_triggered", symbol=symbol, price=current_price, 
                              sl=sl_price, hold_time=f"{hold_time:.0f}s", loss=potential_loss)
                await self._emergency_close(symbol)
                return

            if current_price > pos["max_price_seen"]:
                pos["max_price_seen"] = current_price

            if pnl_pct >= settings.TRAILING_STOP_TRIGGER:
                if not pos["trailing_active"]:
                    pos["trailing_active"] = True
                    self.trailing_activation_time[symbol] = time.time()
                    logger.info("trailing_stop_activated", symbol=symbol, pnl_pct=f"{pnl_pct:.2%}")

            if pos["trailing_active"]:
                if time.time() - self.trailing_activation_time.get(symbol, 0) >= 300:
                    ts_sl = pos["max_price_seen"] * (1 - settings.TRAILING_STOP_TRIGGER)
                    if current_price <= ts_sl:
                        logger.warning("local_ts_triggered", symbol=symbol, price=current_price, ts_sl=ts_sl)
                        await self._profit_close(symbol, reason="TRAILING_STOP")
                        return

        elif side == "Sell":
            sl_price = entry_price * (1 + settings.STOP_LOSS_PCT)
            if current_price >= sl_price:
                potential_loss = abs(unrealized_pnl)
                max_loss_per_exit = getattr(settings, 'MAX_LOSS_PER_EXIT', 5.0)
                
                if potential_loss > max_loss_per_exit:
                    logger.warning("exit_loss_exceeds_max", symbol=symbol,
                                  loss=potential_loss, max_allowed=max_loss_per_exit)
                
                logger.warning("local_sl_triggered", symbol=symbol, price=current_price,
                              sl=sl_price, hold_time=f"{hold_time:.0f}s", loss=potential_loss)
                await self._emergency_close(symbol)
                return

            if current_price < pos["min_price_seen"]:
                pos["min_price_seen"] = current_price

            if pnl_pct >= settings.TRAILING_STOP_TRIGGER:
                if not pos["trailing_active"]:
                    pos["trailing_active"] = True
                    self.trailing_activation_time[symbol] = time.time()

            if pos["trailing_active"]:
                if time.time() - self.trailing_activation_time.get(symbol, 0) >= 300:
                    ts_sl = pos["min_price_seen"] * (1 + settings.TRAILING_STOP_TRIGGER)
                    if current_price >= ts_sl:
                        logger.warning("local_ts_triggered", symbol=symbol, price=current_price, ts_sl=ts_sl)
                        await self._profit_close(symbol, reason="TRAILING_STOP")
                        return

    async def _profit_close(self, symbol: str, reason: str = "PROFIT"):
        """Close position for profit - logs as profitable trade, not emergency."""
        from antigravity.execution import execution_manager
        pos = self.active_positions.get(symbol)
        if not pos:
            return

        logger.info("profit_close_executing", symbol=symbol, reason=reason, side=pos["side"], qty=pos["qty"])
        
        side = "Sell" if pos["side"] == "Buy" else "Buy"
        signal = Signal(
            symbol=symbol,
            type=SignalType.SELL if side == "Sell" else SignalType.BUY,
            price=0.0,
            quantity=pos["qty"],
            reason=reason
        )
        await execution_manager.execute(signal, reason)
        
        if symbol in self.active_positions:
            del self.active_positions[symbol]
            self.position_entry_time.pop(symbol, None)
            self.trailing_activation_time.pop(symbol, None)

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
            self.position_entry_time.pop(symbol, None)
            self.trailing_activation_time.pop(symbol, None)

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

        # 0. Blacklisted symbols check
        if signal.symbol in BLACKLISTED_SYMBOLS:
            logger.warning("risk_block_blacklisted", symbol=signal.symbol, reason="Historical systematic losses")
            return False, f"BLACKLISTED: {signal.symbol} has systematic losses history"

        # 0.5. Session Filter (block American session UTC 16-23)
        current_hour = datetime.now(timezone.utc).hour
        session_blacklist = getattr(settings, 'SESSION_BLACKLIST', [16, 17, 18, 19, 20, 21, 22, 23])
        if current_hour in session_blacklist:
            logger.info("risk_block_session", hour=current_hour, symbol=signal.symbol, 
                       reason="American session blocked")
            return False, f"SESSION_BLOCKED: Hour {current_hour} UTC (American session)"

        # 0.6. Cooldown after loss
        cooldown_after_loss = getattr(settings, 'COOLDOWN_AFTER_LOSS', 900)
        if self._last_loss_time > 0:
            time_since_loss = time.time() - self._last_loss_time
            if time_since_loss < cooldown_after_loss:
                remaining = int(cooldown_after_loss - time_since_loss)
                logger.debug("risk_block_cooldown", remaining_seconds=remaining)
                return False, f"COOLDOWN: {remaining}s remaining after loss"

        # 1. Correlation & Max Positions Check
        active_symbols = [s for s in self.active_positions.keys() if s != signal.symbol]

        if signal.symbol not in self.active_positions:
            # Max 2 positions
            if len(active_symbols) >= 2:
                should_replace, symbol_to_replace = self._should_replace_position(signal, active_symbols)
                if should_replace:
                    logger.info("risk_replacing_position", new=signal.symbol, old=symbol_to_replace)
                    await self._emergency_close(symbol_to_replace)
                    # Refresh active_symbols after closing one
                    active_symbols = [s for s in self.active_positions.keys() if s != signal.symbol]
                else:
                    return False, f"MAX_POSITIONS: 2 positions already active ({', '.join(active_symbols)})"

            # Correlation check
            for active_s in active_symbols:
                if self._are_correlated(signal.symbol, active_s):
                    return False, f"CORRELATED_ASSET: {active_s} is already open"

            # Store quality for handle_order_update
            self.pending_quality[signal.symbol] = self._get_quality_score(signal)

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

        from antigravity.profiles import get_current_profile
        profile = get_current_profile()

        balance = await self._get_balance()
        leverage = signal.leverage if signal.leverage and signal.leverage > 0 else 1.0
        max_leverage = min(profile.max_leverage, settings.MAX_LEVERAGE)
        if leverage > max_leverage:
            leverage = max_leverage
            signal.leverage = leverage

        daily_loss_left = max(0, profile.max_daily_loss - self.current_daily_loss)

        risk_per_trade = getattr(signal, 'risk_percentage', profile.risk_per_trade)
        if risk_per_trade is None or risk_per_trade <= 0:
            risk_per_trade = profile.risk_per_trade

        size_by_pct = balance * risk_per_trade
        size_by_abs = profile.max_position_size

        risk_size = daily_loss_left / profile.stop_loss_pct if profile.stop_loss_pct > 0 else size_by_abs

        target_size = min(size_by_pct, size_by_abs, risk_size)

        regime_data = market_regime_detector.regimes.get(signal.symbol)
        is_volatile = regime_data and regime_data.regime == MarketRegime.VOLATILE

        if profile.enable_spot_mode_for_volatile:
            if self.trading_mode == TradingMode.RECOVERY or is_volatile:
                target_size = min(target_size, balance * 0.20)
                signal.category = "spot"
                signal.leverage = 1.0
                reason = "VOLATILE_REGIME" if is_volatile else "RECOVERY_MODE"
                logger.info("spot_only_mode_active", reason=reason, symbol=signal.symbol, target_size=target_size)

        if signal.price and signal.price > 0:
            MIN_REASONABLE_PRICES = {
                "BTCUSDT": 10000,
                "ETHUSDT": 1000,
                "SOLUSDT": 10,
                "ADAUSDT": 0.1,
                "DOGEUSDT": 0.01
            }
            
            min_expected_price = MIN_REASONABLE_PRICES.get(signal.symbol, 0.001)
            if signal.price < min_expected_price * 0.5 or signal.price > min_expected_price * 100:
                logger.warning("price_anomaly_detected", symbol=signal.symbol, price=signal.price, 
                              expected_min=min_expected_price * 0.5, expected_max=min_expected_price * 100)
                if not profile.is_testnet:
                    return False, f"Price anomaly detected: {signal.price} seems incorrect for {signal.symbol}"
            
            target_qty = target_size / signal.price
            
            MIN_QTY = {
                "BTCUSDT": 0.001,
                "ETHUSDT": 0.01,
                "SOLUSDT": 0.1,
                "ADAUSDT": 1.0,
                "DOGEUSDT": 10.0
            }
            
            min_qty = MIN_QTY.get(signal.symbol, 0.01)
            if target_qty < min_qty:
                target_qty = min_qty
                logger.info("qty_adjusted_to_minimum", symbol=signal.symbol, qty=target_qty, min_qty=min_qty)
            
            if target_size < MIN_ORDER_COST:
                return False, f"Size too small: ${target_size:.2f} < ${MIN_ORDER_COST}"
            signal.quantity = target_qty
        else:
            logger.warning("signal_missing_price", symbol=signal.symbol)
            return False, f"Signal missing valid price for {signal.symbol}"

        signal.stop_loss = signal.price * (1 - profile.stop_loss_pct) if signal.type == SignalType.BUY else signal.price * (1 + profile.stop_loss_pct)

        if signal.price and signal.price > 0 and signal.quantity and signal.quantity > 0:
            position_value = signal.price * signal.quantity
            max_loss_amount = position_value * profile.stop_loss_pct
            if max_loss_amount > profile.max_single_trade_loss:
                logger.warning("risk_block_single_trade_loss", symbol=signal.symbol, 
                             potential_loss=max_loss_amount, max_allowed=profile.max_single_trade_loss)
                return False, f"Potential loss ${max_loss_amount:.2f} exceeds MAX_SINGLE_TRADE_LOSS ${profile.max_single_trade_loss}"

        return True, signal.reason

    async def _close_all_positions(self):
        symbols = list(self.active_positions.keys())
        for s in symbols:
            await self._emergency_close(s)

    def _are_correlated(self, s1: str, s2: str) -> bool:
        for group in CORRELATION_GROUPS.values():
            for pair in group:
                if (s1 == pair[0] and s2 == pair[1]) or (s1 == pair[1] and s2 == pair[0]):
                    return True
        return False

    def _should_replace_position(self, new_signal: Signal, active_symbols: List[str]) -> tuple[bool, Optional[str]]:
        new_quality = self._get_quality_score(new_signal)

        profits = []
        for symbol in active_symbols:
            pos = self.active_positions.get(symbol, {})
            last_price = pos.get("last_price", pos.get("entry_price"))
            side = pos.get("side")
            entry_price = pos.get("entry_price", 1.0)

            pnl_pct = (last_price - entry_price) / entry_price
            if side == "Sell": pnl_pct = -pnl_pct
            profits.append((symbol, pnl_pct, pos.get("quality_score", 2)))

        # Rule: If both existing profitable > 2% -> Reject new signal (don't close winners)
        if all(p[1] > 0.02 for p in profits):
            return False, None

        # Rule: If one losing > -1% (i.e. -2% < pnl < -1%) -> Replace the loser
        # Wait, user said "одна убыточная > -1% → Закрыть убыточную".
        # In Russian "> -1%" for loss usually means "worse than -1%", i.e. PnL < -0.01.
        for symbol, pnl, quality in profits:
            if pnl < -0.01:
                return True, symbol

        # Quality-based replacement
        for symbol, pnl, quality in profits:
            # Type A (3) replaces Type C (1)
            if new_quality >= 3 and quality <= 1:
                return True, symbol

        return False, None

    def _get_quality_score(self, signal: Signal) -> int:
        if "Type A" in signal.reason: return 3
        if "Type B" in signal.reason: return 2
        if "Type C" in signal.reason: return 1
        return 2

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
