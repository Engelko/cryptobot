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

            if signal.type == SignalType.BUY:
                # 2. Determine Trade Size
                # "Take from wallet balance... not more than is on the wallet"
                # Logic: min(Configured_Max, Available_Balance)
                max_size = settings.MAX_POSITION_SIZE
                trade_size = min(available_balance, max_size)

                logger.info("real_trade_sizing", max_size=max_size, available=available_balance, final_size=trade_size)

                # Minimum order size check (approx 10 USDT for Bybit usually)
                if trade_size < 10.0:
                    logger.warning("real_insufficient_funds", available=available_balance, required=10.0)
                    audit.log_event("EXECUTION", f"BUY REJECTED: Low Balance {available_balance:.2f} < 10", "WARNING")
                    return

                # 3. Calculate Quantity
                # For Linear Perp (BTCUSDT), qty is in Base Coin (BTC)
                price = signal.price
                qty = trade_size / price

                # Rounding: Bybit requires specific precision.
                # For safety, we round to 3 decimals. Ideally should fetch instrument info.
                qty_str = f"{qty:.3f}"

                logger.info("real_placing_buy", symbol=signal.symbol, qty=qty_str, expected_price=price)

                # 4. Place Order
                # Market Order for immediate execution
                res = await client.place_order(
                    category="linear",
                    symbol=signal.symbol,
                    side="Buy",
                    orderType="Market",
                    qty=qty_str
                )

                logger.info("real_buy_response", response=res)

                if res and "orderId" in res:
                    logger.info("real_buy_filled", order_id=res["orderId"], qty=qty_str, cost=trade_size)
                    db.save_trade(signal.symbol, "BUY", price, float(qty_str), trade_size, strategy_name, exec_type="REAL")
                    audit.log_event("EXECUTION", f"REAL BUY: {signal.symbol} {qty_str} @ ~{price}", "INFO")
                else:
                    logger.error("real_buy_failed", res=res)
                    audit.log_event("EXECUTION", f"BUY FAILED: {str(res)}", "ERROR")

            elif signal.type == SignalType.SELL:
                # For SELL (Close Position), we need to check if we have an open position first.
                # In this simple bot, SELL usually means "Close Long".
                # We need to know the open size.

                positions = await client.get_positions(category="linear", symbol=signal.symbol)
                # positions is a list
                if not positions:
                     logger.warning("real_sell_no_position", symbol=signal.symbol)
                     return

                # Assuming single position mode or net mode
                # Find position with size > 0
                target_pos = None
                for p in positions:
                    if float(p.get("size", 0)) > 0:
                        target_pos = p
                        break

                if not target_pos:
                    logger.warning("real_sell_no_open_qty", symbol=signal.symbol)
                    return

                qty_to_close = target_pos["size"] # Close full position

                res = await client.place_order(
                    category="linear",
                    symbol=signal.symbol,
                    side="Sell",
                    orderType="Market",
                    qty=qty_to_close
                )

                if res and "orderId" in res:
                    logger.info("real_sell_filled", order_id=res["orderId"], qty=qty_to_close)

                    # Estimate PnL based on position entry price vs current market price (signal price)
                    # This is an approximation as the fill price might differ slightly.
                    try:
                        entry_price = float(target_pos.get("avgPrice", 0.0))
                        exit_price = float(signal.price)
                        qty = float(qty_to_close)

                        # Long PnL = (Exit - Entry) * Qty
                        estimated_pnl = (exit_price - entry_price) * qty

                        logger.info("real_pnl_estimation", entry=entry_price, exit=exit_price, qty=qty, pnl=estimated_pnl)
                    except Exception as ex:
                        logger.warning("real_pnl_estimation_failed", error=str(ex))
                        estimated_pnl = 0.0

                    # Save trade with estimated PnL
                    db.save_trade(signal.symbol, "SELL", signal.price, float(qty_to_close), 0.0, strategy_name, exec_type="REAL", pnl=estimated_pnl)
                    audit.log_event("EXECUTION", f"REAL SELL: {signal.symbol} {qty_to_close} | Est PnL: {estimated_pnl:.2f}", "INFO")

                    # Publish PnL Event for Risk Manager
                    await event_bus.publish(TradeClosedEvent(
                        symbol=signal.symbol,
                        pnl=estimated_pnl,
                        strategy=strategy_name,
                        execution_type="REAL"
                    ))

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
