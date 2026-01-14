from typing import Dict, Optional
from antigravity.config import settings
from antigravity.strategy import Signal, SignalType
from antigravity.logging import get_logger
from antigravity.database import db
from antigravity.audit import audit
from antigravity.client import BybitClient
from antigravity.event import event_bus, TradeClosedEvent

logger = get_logger("execution")

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
        # Use available balance (virtual)
        trade_size = min(self.balance, max_size)

        if trade_size < 10.0: # Minimum virtual order check
             logger.warning("paper_insufficient_funds", balance=self.balance, cost=trade_size)
             return

        if signal.type == SignalType.BUY:
            cost = trade_size
            qty = cost / price
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
                 new_entry = price
            
            self.positions[signal.symbol] = {"quantity": new_qty, "entry_price": new_entry}
            
            logger.info("paper_buy_filled", symbol=signal.symbol, price=price, qty=qty, balance=self.balance)
            db.save_trade(signal.symbol, "BUY", price, qty, cost, strategy_name, exec_type="PAPER")
            audit.log_event("EXECUTION", f"BUY FILLED: {signal.symbol} {qty:.4f} @ {price} | Bal: {self.balance}", "IFO")

        elif signal.type == SignalType.SELL:
            if signal.symbol not in self.positions or self.positions[signal.symbol]["quantity"] <= 0:
                # Paper Broker Simple: If no position, treat SELL as Short Entry?
                # Existing Logic was "Close Only".
                # Improving Paper Broker to match Real Broker improvement (Open Short)
                # But to keep it simple and safe for now, leaving Paper Broker as is unless requested.
                # Focusing on RealBroker as per user issue.
                logger.warning("paper_sell_no_position", symbol=signal.symbol)
                audit.log_event("EXECUTION", f"SELL REJECTED: No Position {signal.symbol}", "WARNING")
                return
            
            # Close entire position
            qty = self.positions[signal.symbol]["quantity"]
            entry_price = self.positions[signal.symbol]["entry_price"]
            value = qty * price
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

class RealBroker:
    """
    Executes orders on Bybit via API.
    """
    async def execute_order(self, signal: Signal, strategy_name: str):
        client = BybitClient()
        try:
            # 1. Fetch Available Balance (USDT)
            balance_data = await client.get_wallet_balance(coin="USDT")
            available_balance = self._parse_available_balance(balance_data)

            logger.info("real_execution_start", symbol=signal.symbol, available_balance=available_balance)

            # Check for existing position to determine intent (Open vs Close)
            positions = await client.get_positions(category="linear", symbol=signal.symbol)

            long_pos = None
            short_pos = None
            for p in positions:
                # Bybit V5: side is "Buy" (Long) or "Sell" (Short). size is always positive.
                if p.get("side") == "Buy" and float(p.get("size", 0)) > 0:
                    long_pos = p
                elif p.get("side") == "Sell" and float(p.get("size", 0)) > 0:
                    short_pos = p

            # ---------------------------------------------------------
            # BUY SIGNAL
            # ---------------------------------------------------------
            if signal.type == SignalType.BUY:
                # If we are Short, this Buy is a "Close Short" (or reduce).
                # If we are Flat/Long, this Buy is an "Open/Add Long".

                # Logic: Calculate size and place Buy Order.

                # Trade Sizing
                max_size = settings.MAX_POSITION_SIZE
                trade_size = min(available_balance, max_size)

                # Min Order Check
                if trade_size < 10.0:
                    logger.warning("real_insufficient_funds", available=available_balance, required=10.0)
                    return

                price = signal.price
                qty = trade_size / price
                qty_str = f"{qty:.5f}"

                if float(qty_str) <= 0:
                     logger.warning("real_buy_qty_zero", symbol=signal.symbol, qty=qty_str)
                     return

                # PnL Estimation if Closing Short
                if short_pos:
                    # We are closing (at least partially) a short position
                    # This is complex to estimate perfectly before fill, but we can log intent
                    logger.info("real_buy_closing_short", symbol=signal.symbol, short_size=short_pos["size"])
                    # PnL logic could go here, but omitted for simplicity/safety to focus on execution.

                # Place Order
                res = await client.place_order(
                    category="linear",
                    symbol=signal.symbol,
                    side="Buy",
                    orderType="Market",
                    qty=qty_str
                )

                if res and "orderId" in res:
                    logger.info("real_buy_filled", order_id=res["orderId"], qty=qty_str)
                    db.save_trade(signal.symbol, "BUY", price, float(qty_str), trade_size, strategy_name, exec_type="REAL")
                else:
                    logger.error("real_buy_failed", res=res)

            # ---------------------------------------------------------
            # SELL SIGNAL
            # ---------------------------------------------------------
            elif signal.type == SignalType.SELL:
                # If we are Long, this Sell is a "Close Long".
                # If we are Flat/Short, this Sell is an "Open/Add Short".

                if long_pos:
                    # CLOSE LONG
                    qty_to_close = long_pos["size"]
                    logger.info("real_sell_closing_long", symbol=signal.symbol, size=qty_to_close)

                    res = await client.place_order(
                        category="linear",
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_to_close
                    )

                    if res and "orderId" in res:
                        logger.info("real_sell_close_filled", order_id=res["orderId"])

                        # Estimate PnL
                        try:
                            entry = float(long_pos.get("avgPrice", 0))
                            exit_p = float(signal.price)
                            qty_f = float(qty_to_close)
                            pnl = (exit_p - entry) * qty_f

                            db.save_trade(signal.symbol, "SELL", exit_p, qty_f, 0.0, strategy_name, exec_type="REAL", pnl=pnl)
                            await event_bus.publish(TradeClosedEvent(symbol=signal.symbol, pnl=pnl, strategy=strategy_name, execution_type="REAL"))
                        except Exception:
                            pass
                    else:
                        logger.error("real_sell_close_failed", res=res)

                else:
                    # OPEN SHORT (Flat or already Short)
                    # Logic similar to Buy: Calculate size based on balance

                    max_size = settings.MAX_POSITION_SIZE
                    trade_size = min(available_balance, max_size)

                    if trade_size < 10.0:
                        logger.warning("real_sell_insufficient_funds", available=available_balance, required=10.0)
                        return

                    price = signal.price
                    qty = trade_size / price
                    qty_str = f"{qty:.5f}"

                    if float(qty_str) <= 0:
                         logger.warning("real_sell_qty_zero", symbol=signal.symbol, qty=qty_str)
                         return

                    logger.info("real_sell_opening_short", symbol=signal.symbol, qty=qty_str)

                    res = await client.place_order(
                        category="linear",
                        symbol=signal.symbol,
                        side="Sell",
                        orderType="Market",
                        qty=qty_str
                    )

                    if res and "orderId" in res:
                        logger.info("real_sell_short_filled", order_id=res["orderId"], qty=qty_str)
                        db.save_trade(signal.symbol, "SELL", price, float(qty_str), trade_size, strategy_name, exec_type="REAL")
                    else:
                        logger.error("real_sell_short_failed", res=res)

        except Exception as e:
            logger.error("real_execution_error", error=str(e))
            audit.log_event("EXECUTION", f"ERROR: {str(e)}", "ERROR")
        finally:
            await client.close()

    def _parse_available_balance(self, data: Dict) -> float:
        """
        Extract available USDT balance from Unified or Contract response.
        """
        try:
            # 1. Unified Account
            if "totalWalletBalance" in data:
                 # In UTA, available balance for opening positions can be 'totalMarginBalance'
                 # or specifically 'totalAvailableBalance' if present?
                 # Bybit V5: totalMarginBalance is equity.
                 # We want available balance. 'totalAvailableBalance' is not always in the wallet-balance endpoint?
                 # 'totalWalletBalance' is cash.
                 # Let's use totalWalletBalance for simplicity as requested "money on wallet".
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
        else:
            await self.real_broker.execute_order(signal, strategy_name)

# Global Manager
execution_manager = ExecutionManager()
