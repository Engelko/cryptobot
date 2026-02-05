from typing import Dict, Optional
from decimal import Decimal, ROUND_DOWN
from typing import List, Dict
from antigravity.config import settings
from antigravity.strategy import Signal, SignalType, TakeProfitLevel
from antigravity.logging import get_logger
from antigravity.database import db
from antigravity.audit import audit
from antigravity.client import BybitClient
from antigravity.event import event_bus, TradeClosedEvent
from antigravity.fees import FeeConfig
from antigravity.utils import safe_float
import uuid
import structlog

logger = get_logger("execution")

class ExecutionRejection(Exception):
    """Base class for business-level order rejections."""
    pass

class LiquidityRejection(ExecutionRejection):
    """Rejected due to spread or depth."""
    pass

class BalanceRejection(ExecutionRejection):
    """Rejected due to insufficient margin/balance."""
    pass

class LeverageRejection(ExecutionRejection):
    """Rejected due to failure to set leverage."""
    pass

# Hardcoded Precision Map for Testnet/Linear
# Based on typical Bybit specs.
# Safe fallback: Floor to these decimals.
PRECISION_MAP = {
    "BTCUSDT": 3,
    "ETHUSDT": 2,
    "SOLUSDT": 1,
    "XRPUSDT": 1,
    "ADAUSDT": 0, # Integer is safer for low value
    "DOGEUSDT": 0,
    "BNBUSDT": 2,
    "MATICUSDT": 0,
    "DOTUSDT": 1,
    "LTCUSDT": 2,
}

class PaperBroker:
    """
    Simulates order execution and tracks a virtual portfolio.
    """
    def __init__(self):
        self.balance = settings.INITIAL_CAPITAL
        self.positions: Dict[str, Dict[str, float]] = {} # symbol -> {quantity, entry_price}

    async def execute_order(self, signal: Signal, strategy_name: str):
        price = signal.price
        
        # Determine Size based on balance and settings
        max_size = settings.MAX_POSITION_SIZE
        
        # Use leverage from signal if available, otherwise default to 1x
        leverage_multiplier = signal.leverage if signal.leverage is not None else 1.0
        
        # Use available balance (virtual)
        trade_size = min(self.balance, max_size)
        if leverage_multiplier > 1.0:
            # Apply leverage: we can trade more than our balance
            trade_size = min(trade_size * leverage_multiplier, max_size * leverage_multiplier)

        if trade_size < 10.0: # Minimum virtual order check
             logger.warning("paper_insufficient_funds", balance=self.balance, cost=trade_size)
             return

        if signal.type == SignalType.BUY:
            cost = trade_size
            safe_price = price if price is not None else 0.0
            if safe_price <= 0:
                logger.error("Invalid price for paper trading")
                return
            qty = cost / safe_price
            self.balance -= cost
            
            # Update Position
            if signal.symbol not in self.positions:
                self.positions[signal.symbol] = {"quantity": 0.0, "entry_price": 0.0}
            
            current_qty = self.positions[signal.symbol]["quantity"]
            current_entry = self.positions[signal.symbol]["entry_price"]
            
             # Avg Entry Price
            new_qty = current_qty + qty
            if new_qty > 0:
                 current_notional = current_qty * current_entry
                 new_entry = (current_notional + cost) / new_qty
            else:
                 new_entry = safe_price
            
            self.positions[signal.symbol] = {"quantity": new_qty, "entry_price": new_entry}
            
            logger.info("paper_buy_filled", symbol=signal.symbol, price=safe_price, qty=qty, balance=self.balance)
            db.save_trade(signal.symbol, "BUY", safe_price, qty, cost, strategy_name, exec_type="PAPER")
            audit.log_event("EXECUTION", f"BUY FILLED: {signal.symbol} {qty:.4f} @ {safe_price} | Bal: {self.balance}", "IFO")
            
            # Store take profit levels for paper trading simulation
            if signal.take_profit_levels:
                if not hasattr(self, 'pending_take_profits'):
                    self.pending_take_profits = {}
                self.pending_take_profits[signal.symbol] = {
                    'levels': signal.take_profit_levels,
                    'original_qty': qty,
                    'remaining_qty': qty,
                    'side': 'Buy'
                }

        elif signal.type == SignalType.SELL:
            if signal.symbol not in self.positions or self.positions[signal.symbol]["quantity"] <= 0:
                logger.warning("paper_sell_no_position", symbol=signal.symbol)
                audit.log_event("EXECUTION", f"SELL REJECTED: No Position {signal.symbol}", "WARNING")
                return
            
            # Close entire position
            qty = self.positions[signal.symbol]["quantity"]
            entry_price = self.positions[signal.symbol]["entry_price"] or 0.0
            safe_price = price if price is not None else 0.0
            if safe_price <= 0:
                logger.error("Invalid price for paper trading sell")
                return
            value = qty * safe_price
            cost = qty * entry_price
            pnl = value - cost
            
            self.balance += value
            del self.positions[signal.symbol]
            
            logger.info("paper_sell_filled", symbol=signal.symbol, price=price, qty=qty, pnl=pnl, balance=self.balance)
            db.save_trade(signal.symbol, "SELL", price, qty, value, strategy_name, exec_type="PAPER", pnl=pnl)
            audit.log_event("EXECUTION", f"SELL FILLED: {signal.symbol} {qty:.4f} @ {price} | PnL: {pnl:.2f}", "INFO")

            # Publish PnL Event for Risk Manager
            await event_bus.publish(TradeClosedEvent(
                symbol=signal.symbol,
                pnl=pnl,
                strategy=strategy_name,
                execution_type="PAPER"
            ))

    def check_take_profit_triggers(self, symbol: str, current_price: float):
        """
        Check and execute pending take-profit orders for paper trading
        """
        if not hasattr(self, 'pending_take_profits') or symbol not in self.pending_take_profits:
            return
            
        tp_info = self.pending_take_profits[symbol]
        if tp_info['remaining_qty'] <= 0:
            return
            
        levels_triggered = []
        for level in tp_info['levels']:
            if level.quantity_percentage > 0:  # Not yet executed
                if tp_info['side'] == 'Buy' and current_price >= level.price:
                    levels_triggered.append(level)
                elif tp_info['side'] == 'Sell' and current_price <= level.price:
                    levels_triggered.append(level)
        
        # Execute triggered levels
        for level in levels_triggered:
            tp_quantity = tp_info['original_qty'] * level.quantity_percentage
            
            # Calculate PnL for this partial close
            if symbol in self.positions:
                entry_price = self.positions[symbol]['entry_price'] or 0.0
                if tp_info['side'] == 'Buy':
                    pnl = (current_price - entry_price) * tp_quantity
                else:
                    pnl = (entry_price - current_price) * tp_quantity
                
                # Update position
                self.positions[symbol]['quantity'] -= tp_quantity
                self.balance += tp_quantity * current_price
                
                logger.info(f"paper_tp_filled: {symbol} {tp_quantity:.6f} @ ${current_price} | PnL: ${pnl:.2f}")
                
                # Mark level as executed
                level.quantity_percentage = 0

class RealBroker:
    """
    Executes orders on Bybit via API.
    """
    async def _check_liquidity(self, symbol: str, category: str, qty: float) -> bool:
        client = BybitClient()
        try:
            ob = await client.get_orderbook(symbol, category)
            bids = ob.get("b", [])
            asks = ob.get("a", [])

            if not bids or not asks:
                return False

            best_bid = safe_float(bids[0][0])
            best_ask = safe_float(asks[0][0])
            if best_bid <= 0: return False
            spread = (best_ask - best_bid) / best_bid

            if spread > settings.MAX_SPREAD:
                logger.warning("liquidity_check_failed", symbol=symbol, reason="spread_too_high", spread=spread, limit=settings.MAX_SPREAD)
                raise LiquidityRejection(f"Spread too high: {spread:.4%}")

            # Depth check: Top 3 levels > 2x order size
            depth_bids = sum(safe_float(b[1]) for b in bids[:3])
            depth_asks = sum(safe_float(a[1]) for a in asks[:3])

            if depth_bids < 2 * qty or depth_asks < 2 * qty:
                logger.warning("liquidity_check_failed", symbol=symbol, reason="insufficient_depth",
                               depth_bids=depth_bids, depth_asks=depth_asks, required=2*qty)
                raise LiquidityRejection(f"Insufficient depth: bids={depth_bids:.2f}, asks={depth_asks:.2f}, req={2*qty:.2f}")

            return True
        except Exception as e:
            logger.error("liquidity_check_error", error=str(e))
            return False
        finally:
            await client.close()

    async def execute_order(self, signal: Signal, strategy_name: str):
        client = BybitClient()
        category = signal.category

        try:
            # Generate Trace ID for logs if not present
            trace_id = getattr(signal, "trace_id", str(uuid.uuid4()))

            # Bind trace_id to logger context for this execution
            # Note: structlog thread-local context binding works, but here we just pass it manually or bind logger
            log = logger.bind(trace_id=trace_id, strategy=strategy_name)

            # 1. Fetch Available Balance (USDT)
            balance_data = await client.get_wallet_balance(coin="USDT")
            available_balance = self._parse_available_balance(balance_data)

            log.info("real_execution_start", symbol=signal.symbol, available_balance=available_balance)

            # Ensure we have a valid price for PnL estimation and sizing
            if not signal.price or signal.price <= 0:
                try:
                    ticker = await client.get_ticker(signal.symbol, category)
                    signal.price = safe_float(ticker.get("lastPrice", 0))
                    log.info("market_order_price_estimated", symbol=signal.symbol, estimated_price=signal.price)
                except Exception as e:
                    log.error("ticker_fetch_failed_for_estimation", error=str(e))

            # Check for existing position to determine intent (Open vs Close)
            # Bybit V5: get_positions only supports linear or option. Spot uses wallet balance.
            positions = []
            if category != "spot":
                try:
                    positions = await client.get_positions(category=category, symbol=signal.symbol)
                except Exception as e:
                    log.error("real_execution_abort_api_error", error=f"Failed to fetch positions: {str(e)}")
                    return

            long_pos = None
            short_pos = None
            for p in positions:
                size = safe_float(p.get("size", 0))
                if p.get("side") == "Buy" and size > 0:
                    long_pos = p
                elif p.get("side") == "Sell" and size > 0:
                    short_pos = p

            # ---------------------------------------------------------
            # BUY SIGNAL
            # ---------------------------------------------------------
            if signal.type == SignalType.BUY:
                if short_pos:
                    # CLOSE SHORT
                    qty_to_close = short_pos["size"]
                    log.info("real_buy_closing_short", symbol=signal.symbol, size=qty_to_close)

                    safe_trace_id = trace_id.replace("-", "")[:30]
                    res = await client.place_order(
                        category=category,
                        symbol=signal.symbol,
                        side="Buy",
                        orderType="Market",
                        qty=qty_to_close,
                        orderLinkId=f"{safe_trace_id}-cs"
                    )

                    if res and "orderId" in res:
                        log.info("real_buy_close_short_filled", order_id=res["orderId"])
                        # Estimate PnL
                        try:
                            entry = safe_float(short_pos.get("avgPrice", 0))
                            exit_p = safe_float(signal.price)
                            qty_f = safe_float(qty_to_close)
                            pnl = (entry - exit_p) * qty_f
                            fees = FeeConfig.estimate_fee(qty_f, entry, "linear") + FeeConfig.estimate_fee(qty_f, exit_p, "linear")
                            net_pnl = pnl - fees
                            db.save_trade(signal.symbol, "BUY", exit_p, qty_f, 0.0, strategy_name, exec_type="REAL", pnl=net_pnl)
                            await event_bus.publish(TradeClosedEvent(symbol=signal.symbol, pnl=net_pnl, strategy=strategy_name, execution_type="REAL"))
                        except Exception as e:
                            log.error("short_pnl_estimation_error", error=str(e))

                if signal.reason == "LOCAL_CASCADE_STOP" or signal.reason == "RiskManager_Emergency":
                    return

                # Trade Sizing
                max_size = settings.MAX_POSITION_SIZE
                
                # Use leverage from signal if available, otherwise default to 1x
                leverage_multiplier = signal.leverage if signal.leverage is not None else 1.0
                
                # SET LEVERAGE ON EXCHANGE (Linear only)
                if category == "linear" and signal.leverage and signal.leverage > 0:
                    leverage_set_success = await self._set_leverage(signal.symbol, signal.leverage)
                    if not leverage_set_success:
                        log.error("leverage_set_failed_abort", symbol=signal.symbol, requested=signal.leverage)
                        # Save execution failure to DB
                        db.save_trade(
                            symbol=signal.symbol,
                            side="BUY",
                            price=signal.price or 0.0,
                            qty=0.0,
                            val=0.0,
                            strat=strategy_name,
                            exec_type="FAILED",
                            pnl=0.0
                        )
                        # ABORT: Do not execute trade with incorrect leverage
                        raise LeverageRejection(f"Failed to set leverage to {signal.leverage}x")
                    else:
                        log.info("leverage_set_success", symbol=signal.symbol, leverage=f"{signal.leverage}x")
                
                # Determine Trade Size
                # If signal has quantity, use it (RiskManager has already validated/resized it)
                # Fallback to maximizing logic if quantity is missing
                price = signal.price if signal.price is not None else 0.0
                if price <= 0:
                    log.error("Invalid price for signal")
                    return

                if signal.quantity and signal.quantity > 0:
                    qty = signal.quantity
                    # Double check safety (clamp to max_size just in case)
                    notional = qty * price
                    if notional > max_size:
                        qty = max_size / price
                        log.warning("real_buy_clamped_max_size", original=signal.quantity, clamped=qty)

                    # Also clamp to available balance (margin check)
                    # available_balance is the USDT available.
                    # required_margin = notional / leverage
                    required_margin = (qty * price) / leverage_multiplier
                    if required_margin > available_balance:
                        # Resize to fit balance
                        qty = (available_balance * leverage_multiplier) / price
                        log.warning("real_buy_clamped_balance", original=signal.quantity, clamped=qty, balance=available_balance)

                    trade_size = qty * price
                else:
                    # Legacy logic: Maximize trade
                    # STRICT FIX: MAX_POSITION_SIZE is NOTIONAL limit.
                    # We can use up to max_size USDT of value.
                    # Margin required = max_size / leverage.
                    # If Margin required > Available Balance, we are limited by balance.

                    # 1. Cap by Notional Limit (Budget)
                    target_notional = max_size

                    # 2. Cap by Available Margin
                    # Max notional allowed by wallet = Balance * Leverage
                    wallet_max_notional = available_balance * leverage_multiplier

                    trade_size = min(target_notional, wallet_max_notional)
                    qty = trade_size / price

                # Min Order Check
                if trade_size < 10.0:
                    log.warning("real_insufficient_funds", available=available_balance, required=10.0, planned_trade_size=trade_size)
                    raise BalanceRejection(f"Insufficient funds: trade size ${trade_size:.2f} < $10.0")

                qty_str = self._format_qty(signal.symbol, qty)

                qty_f = safe_float(qty_str)
                if qty_f <= 0:
                     log.warning("real_buy_qty_zero", symbol=signal.symbol, qty=qty_str)
                     return

                # Liquidity Check
                if not await self._check_liquidity(signal.symbol, category, qty_f):
                    log.warning("real_buy_liquidity_fail_abort", symbol=signal.symbol)
                    return

                # Calculate Estimated Fees
                estimated_fee = FeeConfig.estimate_fee(qty_f, price, "linear", is_maker=False)
                log.info("fee_estimation", symbol=signal.symbol, side="Buy", fee=estimated_fee)

                # Place Order with Cascade Stops
                safe_trace_id = trace_id.replace("-", "")[:30]
                order_link_id = f"{safe_trace_id}-buy"

                if category == "spot":
                    # Spot Market Buy: qty is USDT
                    # We use trade_size directly
                    spot_qty_str = str(round(trade_size, 2))
                    res = await client.place_order(
                        category="spot",
                        symbol=signal.symbol,
                        side="Buy",
                        orderType="Market",
                        qty=spot_qty_str,
                        orderLinkId=order_link_id
                    )
                else:
                    # Level 1: Hard SL and Trailing Stop
                    sl_price = self._format_price(signal.symbol, signal.stop_loss) if hasattr(signal, "stop_loss") and signal.stop_loss else None
                    # Trailing stop trigger at +1.5%
                    ts_dist = self._format_price(signal.symbol, price * settings.TRAILING_STOP_TRIGGER)

                    res = await client.place_order(
                        category=category,
                        symbol=signal.symbol,
                        side="Buy",
                        orderType="Market",
                        qty=qty_str,
                        orderLinkId=order_link_id,
                        stopLoss=sl_price,
                        trailingStop=ts_dist
                    )

                if res and "orderId" in res:
                    log.info("real_buy_filled", order_id=res["orderId"], qty=qty_str, order_link_id=order_link_id)
                    db.save_trade(signal.symbol, "BUY", price, qty_f, trade_size, strategy_name, exec_type="REAL")
                    
                    # Create partial take-profit orders if provided
                    if signal.take_profit_levels:
                        await self._create_partial_take_profit_orders(
                            signal.symbol, "Buy", qty_f, signal.take_profit_levels, price
                        )
                else:
                    log.error("real_buy_failed", res=res)

            # ---------------------------------------------------------
            # SELL SIGNAL
            # ---------------------------------------------------------
            elif signal.type == SignalType.SELL:
                if category == "spot":
                    # Spot Market Sell: qty is base coin
                    # We need to find how much we have.
                    base_coin = signal.symbol.replace("USDT", "")
                    balance_data = await client.get_wallet_balance(coin=base_coin)
                    # Extract coin balance
                    coin_qty = 0.0
                    if "coin" in balance_data:
                        for c in balance_data["coin"]:
                             if c["coin"] == base_coin:
                                 coin_qty = safe_float(c.get("walletBalance", 0))

                    if coin_qty <= 0:
                        log.warning("spot_sell_no_balance", symbol=signal.symbol)
                        raise BalanceRejection(f"No spot balance for {base_coin}")

                    qty_str = self._format_qty(signal.symbol, coin_qty)
                    res = await client.place_order(
                        category="spot",
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_str,
                        orderLinkId=f"{trace_id[:30]}-spot-sell"
                    )
                    if res and "orderId" in res:
                        log.info("spot_sell_filled", order_id=res["orderId"])
                        # Calculate PnL for Spot
                        net_pnl = 0.0
                        exit_p = signal.price or 0.0
                        qty_f = safe_float(qty_str)

                        last_buy = db.get_last_trade(signal.symbol, "BUY")
                        if last_buy:
                            entry = last_buy["price"]
                            gross_pnl = (exit_p - entry) * qty_f
                            # Approx fees
                            fees = FeeConfig.estimate_fee(qty_f, entry, "spot") + FeeConfig.estimate_fee(qty_f, exit_p, "spot")
                            net_pnl = gross_pnl - fees
                            log.info("spot_pnl_calc", gross_pnl=gross_pnl, fees=fees, net_pnl=net_pnl)

                        db.save_trade(signal.symbol, "SELL", exit_p, qty_f, 0.0, strategy_name, exec_type="REAL", pnl=net_pnl)
                        await event_bus.publish(TradeClosedEvent(symbol=signal.symbol, pnl=net_pnl, strategy=strategy_name, execution_type="REAL"))

                    return

                if long_pos:
                    # CLOSE LONG
                    qty_to_close = long_pos["size"]
                    log.info("real_sell_closing_long", symbol=signal.symbol, size=qty_to_close)

                    safe_trace_id = trace_id.replace("-", "")[:30]
                    order_link_id = f"{safe_trace_id}-cl"

                    res = await client.place_order(
                        category=category,
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_to_close,
                        orderLinkId=order_link_id
                    )

                    if res and "orderId" in res:
                        log.info("real_sell_close_filled", order_id=res["orderId"])

                        # Estimate PnL
                        try:
                            entry = safe_float(long_pos.get("avgPrice", 0))
                            exit_p = safe_float(signal.price)
                            qty_f = safe_float(qty_to_close)
                            pnl = (exit_p - entry) * qty_f
                            fees = FeeConfig.estimate_fee(qty_f, entry, "linear") + FeeConfig.estimate_fee(qty_f, exit_p, "linear")
                            net_pnl = pnl - fees
                            db.save_trade(signal.symbol, "SELL", exit_p, qty_f, 0.0, strategy_name, exec_type="REAL", pnl=net_pnl)
                            await event_bus.publish(TradeClosedEvent(symbol=signal.symbol, pnl=net_pnl, strategy=strategy_name, execution_type="REAL"))
                        except Exception as e:
                            log.error("long_pnl_estimation_error", error=str(e))
                    else:
                        log.error("real_sell_close_failed", res=res)

                if signal.reason == "LOCAL_CASCADE_STOP" or signal.reason == "RiskManager_Emergency":
                    return

                # OPEN SHORT (Flat or already Short)
                max_size = settings.MAX_POSITION_SIZE

                # Use leverage from signal if available, otherwise default to 1x
                leverage_multiplier = signal.leverage if signal.leverage is not None else 1.0

                # SET LEVERAGE ON EXCHANGE before placing order
                if category == "linear" and signal.leverage and signal.leverage > 0:
                    leverage_set_success = await self._set_leverage(signal.symbol, signal.leverage)
                    if not leverage_set_success:
                        log.error("leverage_set_failed_abort", symbol=signal.symbol, requested=signal.leverage)
                        # Save execution failure to DB
                        db.save_trade(
                            symbol=signal.symbol,
                            side="SELL",
                            price=signal.price or 0.0,
                            qty=0.0,
                            val=0.0,
                            strat=strategy_name,
                            exec_type="FAILED",
                            pnl=0.0
                        )
                        # ABORT: Do not execute trade with incorrect leverage
                        raise LeverageRejection(f"Failed to set leverage to {signal.leverage}x")
                    else:
                        log.info("leverage_set_success", symbol=signal.symbol, leverage=f"{signal.leverage}x")

                price = signal.price if signal.price is not None else 0.0
                if price <= 0:
                    log.error("Invalid price for signal")
                    return

                if signal.quantity and signal.quantity > 0:
                    qty = signal.quantity
                    # Double check safety (clamp to max_size just in case)
                    notional = qty * price
                    if notional > max_size:
                        qty = max_size / price
                        log.warning("real_sell_clamped_max_size", original=signal.quantity, clamped=qty)

                    # Also clamp to available balance (margin check)
                    required_margin = (qty * price) / leverage_multiplier
                    if required_margin > available_balance:
                        # Resize to fit balance
                        qty = (available_balance * leverage_multiplier) / price
                        log.warning("real_sell_clamped_balance", original=signal.quantity, clamped=qty, balance=available_balance)

                    trade_size = qty * price
                else:
                    # Legacy logic: Maximize trade
                    # STRICT FIX: MAX_POSITION_SIZE is NOTIONAL limit.

                    # 1. Cap by Notional Limit (Budget)
                    target_notional = max_size

                    # 2. Cap by Available Margin
                    wallet_max_notional = available_balance * leverage_multiplier

                    trade_size = min(target_notional, wallet_max_notional)
                    qty = trade_size / price

                if trade_size < 10.0:
                    log.warning("real_sell_insufficient_funds", available=available_balance, required=10.0, planned_trade_size=trade_size)
                    raise BalanceRejection(f"Insufficient funds: trade size ${trade_size:.2f} < $10.0")

                qty_str = self._format_qty(signal.symbol, qty)
                qty_f = safe_float(qty_str)

                if qty_f <= 0:
                     log.warning("real_sell_qty_zero", symbol=signal.symbol, qty=qty_str)
                     return

                # Liquidity Check
                if not await self._check_liquidity(signal.symbol, category, qty_f):
                    log.warning("real_sell_liquidity_fail_abort", symbol=signal.symbol)
                    return

                log.info("real_sell_opening_short", symbol=signal.symbol, qty=qty_str)

                # Calculate Estimated Fees
                estimated_fee = FeeConfig.estimate_fee(qty_f, price, "linear", is_maker=False)
                log.info("fee_estimation", symbol=signal.symbol, side="Sell", fee=estimated_fee)

                # Place Order with Cascade Stops
                safe_trace_id = trace_id.replace("-", "")[:30]
                order_link_id = f"{safe_trace_id}-open-short"

                # Level 1: Hard SL and Trailing Stop
                sl_price = self._format_price(signal.symbol, signal.stop_loss) if hasattr(signal, "stop_loss") and signal.stop_loss else None
                ts_dist = self._format_price(signal.symbol, price * settings.TRAILING_STOP_TRIGGER)

                res = await client.place_order(
                    category=category,
                    symbol=symbol if (symbol := signal.symbol) else "",
                    side="Sell",
                    orderType="Market",
                    qty=qty_str,
                    orderLinkId=order_link_id,
                    stopLoss=sl_price,
                    trailingStop=ts_dist
                )

                if res and "orderId" in res:
                    log.info("real_sell_short_filled", order_id=res["orderId"], qty=qty_str, order_link_id=order_link_id)
                    db.save_trade(signal.symbol, "SELL", price, qty_f, trade_size, strategy_name, exec_type="REAL")

                    # Create partial take-profit orders if provided
                    if signal.take_profit_levels:
                        if price > 0:
                            await self._create_partial_take_profit_orders(
                                signal.symbol, "Sell", qty_f, signal.take_profit_levels, price
                            )
                else:
                    log.error("real_sell_short_failed", res=res)

        except ExecutionRejection:
            # Re-raise business rejections to be handled by engine
            raise
        except Exception as e:
            # Check if 'log' is bound (in case exception happened before binding)
            if 'log' in locals():
                log.error("real_execution_error", error=str(e))
            else:
                logger.error("real_execution_error", error=str(e))
            audit.log_event("EXECUTION", f"ERROR: {str(e)}", "ERROR")
            raise
        finally:
            await client.close()

    async def _create_partial_take_profit_orders(self, symbol: str, side: str, 
                                                 total_quantity: float, 
                                                 take_profit_levels: List[TakeProfitLevel],
                                                 entry_price: float):
        """
        Create partial take-profit limit orders for the position
        """
        client = BybitClient()
        try:
            for i, tp_level in enumerate(take_profit_levels, 1):
                # Calculate quantity for this TP level
                tp_quantity = total_quantity * tp_level.quantity_percentage
                
                # Determine TP order side (opposite of position side)
                tp_side = "Sell" if side == "Buy" else "Buy"
                
                # Format quantity
                qty_str = self._format_qty(symbol, tp_quantity)
                
                # Create limit order for take profit
                res = await client.place_order(
                    category="linear",
                    symbol=symbol,
                    side=tp_side,
                    orderType="Limit",
                    qty=qty_str,
                    price=str(tp_level.price),
                    timeInForce="PostOnly"  # Only allows post-only orders for take-profit
                )
                
                if res and "orderId" in res:
                    logger.info(f"TP{i} order created: {tp_quantity:.6f} @ ${tp_level.price} ({tp_level.quantity_percentage*100:.0f}%) - {tp_level.reason}")
                else:
                    logger.error(f"TP{i} order failed: {res}")
                    
        except Exception as e:
            logger.error(f"Failed to create take-profit orders: {e}")
        finally:
            await client.close()

    async def _set_leverage(self, symbol: str, leverage: float) -> bool:
        """
        Set leverage for a symbol on the exchange
        """
        client = BybitClient()
        try:
            leverage_str = str(leverage)
            success = await client.set_leverage(
                category="linear",
                symbol=symbol,
                leverage=leverage_str
            )
            return success
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False
        finally:
            await client.close()

    def _format_qty(self, symbol: str, qty: float) -> str:
        """
        Formats quantity to the correct precision for the symbol using floor rounding.
        """
        precision = PRECISION_MAP.get(symbol, 2) # Default to 2 decimals if unknown

        try:
            d = Decimal(str(qty))
            if precision == 0:
                quantizer = Decimal("1")
            else:
                quantizer = Decimal("0.1") ** precision

            rounded = d.quantize(quantizer, rounding=ROUND_DOWN)

            # Format avoiding scientific notation
            return f"{rounded:f}"
        except Exception as e:
            logger.error("qty_format_error", symbol=symbol, error=str(e))
            # Fallback to simple string format
            return f"{qty:.{precision}f}"

    PRICE_PRECISION = {
        "BTCUSDT": 2,
        "ETHUSDT": 2,
        "SOLUSDT": 2,
        "XRPUSDT": 4,
        "ADAUSDT": 4,
        "DOGEUSDT": 5,
        "BNBUSDT": 2,
        "MATICUSDT": 4,
        "DOTUSDT": 3,
        "LTCUSDT": 2,
    }

    def _format_price(self, symbol: str, price: float) -> str:
        """Formats price to appropriate precision."""
        precision = self.PRICE_PRECISION.get(symbol, 2)
        return f"{price:.{precision}f}"

    def _parse_available_balance(self, data: Dict) -> float:
        """
        Extract available USDT balance from Unified or Contract response.
        """
        try:
            # 1. Unified Account
            if "totalWalletBalance" in data:
                 return safe_float(data.get("totalWalletBalance", 0.0))

            # 2. Contract Account
            elif "coin" in data:
                for c in data["coin"]:
                    if c.get("coin") == "USDT":
                        return safe_float(c.get("walletBalance", 0.0))

        except Exception:
            pass
        return 0.0

class ExecutionManager:
    """
    Routes orders to the appropriate broker.
    """
    def __init__(self):
        self.paper_broker = PaperBroker()
        self.real_broker = RealBroker()

    async def execute(self, signal: Signal, strategy_name: str):
        if settings.SIMULATION_MODE:
            await self.paper_broker.execute_order(signal, strategy_name)
            # Check for any pending take-profit triggers after order execution
            self.paper_broker.check_take_profit_triggers(signal.symbol, signal.price or 0.0)
        else:
            await self.real_broker.execute_order(signal, strategy_name)
    
    def check_all_take_profits(self, symbol_prices: Dict[str, float]):
        """
        Check all pending take-profit orders against current prices
        """
        if settings.SIMULATION_MODE:
            for symbol, price in symbol_prices.items():
                self.paper_broker.check_take_profit_triggers(symbol, price)

# Global Manager
execution_manager = ExecutionManager()
