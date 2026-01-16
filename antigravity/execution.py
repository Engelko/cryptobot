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
import uuid
import structlog

logger = get_logger("execution")

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
    async def execute_order(self, signal: Signal, strategy_name: str):
        client = BybitClient()
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

            # Check for existing position to determine intent (Open vs Close)
            positions = await client.get_positions(category="linear", symbol=signal.symbol)

            long_pos = None
            short_pos = None
            for p in positions:
                if p.get("side") == "Buy" and float(p.get("size", 0)) > 0:
                    long_pos = p
                elif p.get("side") == "Sell" and float(p.get("size", 0)) > 0:
                    short_pos = p

            # ---------------------------------------------------------
            # BUY SIGNAL
            # ---------------------------------------------------------
            if signal.type == SignalType.BUY:
                # Trade Sizing
                max_size = settings.MAX_POSITION_SIZE
                
                # Use leverage from signal if available, otherwise default to 1x
                leverage_multiplier = signal.leverage if signal.leverage is not None else 1.0
                
                # SET LEVERAGE ON EXCHANGE before placing order
                if signal.leverage and signal.leverage > 0:
                    leverage_set_success = await self._set_leverage(signal.symbol, signal.leverage)
                    if not leverage_set_success:
                        log.warning("leverage_set_failed_continue", symbol=signal.symbol, requested=signal.leverage)
                        # Don't return! Continue with order execution anyway
                    else:
                        log.info("leverage_set_success", symbol=signal.symbol, leverage=f"{signal.leverage}x")
                
                # Calculate effective position size with leverage
                trade_size = min(available_balance, max_size)
                if leverage_multiplier > 1.0:
                    # Apply leverage: we can trade more than our balance
                    trade_size = min(trade_size * leverage_multiplier, max_size * leverage_multiplier)

                # Min Order Check
                if trade_size < 10.0:
                    log.warning("real_insufficient_funds", available=available_balance, required=10.0)
                    return

                price = signal.price if signal.price is not None else 0.0
                if price <= 0:
                    log.error("Invalid price for signal")
                    return
                qty = trade_size / price
                qty_str = self._format_qty(signal.symbol, qty)

                if float(qty_str) <= 0:
                     log.warning("real_buy_qty_zero", symbol=signal.symbol, qty=qty_str)
                     return

                # Place Order
                # Idempotency: Generate orderLinkId
                order_link_id = f"{trace_id}-buy"

                res = await client.place_order(
                    category="linear",
                    symbol=signal.symbol,
                    side="Buy",
                    orderType="Market",
                    qty=qty_str,
                    orderLinkId=order_link_id
                )

                if res and "orderId" in res:
                    log.info("real_buy_filled", order_id=res["orderId"], qty=qty_str, order_link_id=order_link_id)
                    db.save_trade(signal.symbol, "BUY", price, float(qty_str), trade_size, strategy_name, exec_type="REAL")
                    
                    # Create partial take-profit orders if provided
                    if signal.take_profit_levels:
                        await self._create_partial_take_profit_orders(
                            signal.symbol, "Buy", float(qty_str), signal.take_profit_levels, price
                        )
                else:
                    log.error("real_buy_failed", res=res)

            # ---------------------------------------------------------
            # SELL SIGNAL
            # ---------------------------------------------------------
            elif signal.type == SignalType.SELL:
                if long_pos:
                    # CLOSE LONG
                    qty_to_close = long_pos["size"] # Already formatted by API?
                    # API returns string, usually correct format. But let's be safe?
                    # Usually closing matches open size exactly.

                    log.info("real_sell_closing_long", symbol=signal.symbol, size=qty_to_close)

                    # Idempotency: Generate orderLinkId
                    order_link_id = f"{trace_id}-close-long"

                    res = await client.place_order(
                        category="linear",
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_to_close,
                        orderLinkId=order_link_id
                    )

                    if res and "orderId" in res:
                        log.info("real_sell_close_filled", order_id=res["orderId"], order_link_id=order_link_id)

                        # Estimate PnL
                        try:
                            entry = float(long_pos.get("avgPrice", 0) or 0)
                            exit_p = float(signal.price or 0)
                            qty_f = float(qty_to_close or 0)
                            pnl = (exit_p - entry) * qty_f

                            db.save_trade(signal.symbol, "SELL", exit_p, qty_f, 0.0, strategy_name, exec_type="REAL", pnl=pnl)
                            await event_bus.publish(TradeClosedEvent(symbol=signal.symbol, pnl=pnl, strategy=strategy_name, execution_type="REAL"))
                        except Exception:
                            pass
                    else:
                        log.error("real_sell_close_failed", res=res)

                else:
                    # OPEN SHORT (Flat or already Short)
                    max_size = settings.MAX_POSITION_SIZE
                    
                    # Use leverage from signal if available, otherwise default to 1x
                    leverage_multiplier = signal.leverage if signal.leverage is not None else 1.0
                    
                    # SET LEVERAGE ON EXCHANGE before placing order
                    if signal.leverage and signal.leverage > 0:
                        leverage_set_success = await self._set_leverage(signal.symbol, signal.leverage)
                        if not leverage_set_success:
                            log.warning("leverage_set_failed_continue", symbol=signal.symbol, requested=signal.leverage)
                            # Don't return! Continue with order execution anyway
                        else:
                            log.info("leverage_set_success", symbol=signal.symbol, leverage=f"{signal.leverage}x")
                    
                    # Calculate effective position size with leverage
                    trade_size = min(available_balance, max_size)
                    if leverage_multiplier > 1.0:
                        # Apply leverage: we can trade more than our balance
                        trade_size = min(trade_size * leverage_multiplier, max_size * leverage_multiplier)

                    if trade_size < 10.0:
                        log.warning("real_sell_insufficient_funds", available=available_balance, required=10.0)
                        return

                    price = signal.price if signal.price is not None else 0.0
                    if price <= 0:
                        log.error("Invalid price for signal")
                        return
                    qty = trade_size / price
                    qty_str = self._format_qty(signal.symbol, qty)

                    if float(qty_str) <= 0:
                         log.warning("real_sell_qty_zero", symbol=signal.symbol, qty=qty_str)
                         return

                    log.info("real_sell_opening_short", symbol=signal.symbol, qty=qty_str)

                    # Idempotency
                    order_link_id = f"{trace_id}-open-short"

                    res = await client.place_order(
                        category="linear",
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_str,
                        orderLinkId=order_link_id
                    )

                    if res and "orderId" in res:
                        log.info("real_sell_short_filled", order_id=res["orderId"], qty=qty_str, order_link_id=order_link_id)
                        db.save_trade(signal.symbol, "SELL", price, float(qty_str), trade_size, strategy_name, exec_type="REAL")
                        
                        # Create partial take-profit orders if provided
                        if signal.take_profit_levels:
                            if price > 0:
                                await self._create_partial_take_profit_orders(
                                    signal.symbol, "Sell", float(qty_str), signal.take_profit_levels, price
                                )
                    else:
                        log.error("real_sell_short_failed", res=res)

        except Exception as e:
            # Check if 'log' is bound (in case exception happened before binding)
            if 'log' in locals():
                log.error("real_execution_error", error=str(e))
            else:
                logger.error("real_execution_error", error=str(e))
            audit.log_event("EXECUTION", f"ERROR: {str(e)}", "ERROR")
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

    def _parse_available_balance(self, data: Dict) -> float:
        """
        Extract available USDT balance from Unified or Contract response.
        """
        try:
            # 1. Unified Account
            if "totalWalletBalance" in data:
                 return float(data.get("totalWalletBalance", 0.0))

            # 2. Contract Account
            elif "coin" in data:
                for c in data["coin"]:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))

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
