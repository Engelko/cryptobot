from typing import Dict, Optional
from antigravity.config import settings
from antigravity.strategy import Signal, SignalType
from antigravity.logging import get_logger
from antigravity.database import db
from antigravity.audit import audit

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
        # Default Quantity Logic (Simplified: Fixed notional)
        position_size_usdt = 1000.0
        
        if signal.type == SignalType.BUY:
            cost = position_size_usdt
            if self.balance < cost:
                logger.warning("paper_insufficient_funds", balance=self.balance, cost=cost)
                audit.log_event("EXECUTION", f"BUY REJECTED: Insufficient Funds {self.balance} < {cost}", "WARNING")
                return
            
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

class ExecutionManager:
    """
    Routes orders to the appropriate broker.
    """
    def __init__(self):
        self.paper_broker = PaperBroker()
        self.is_simulation = settings.SIMULATION_MODE

    async def execute(self, signal: Signal, strategy_name: str):
        if self.is_simulation:
            await self.paper_broker.execute_order(signal, strategy_name)
        else:
            logger.warning("real_execution_not_implemented", symbol=signal.symbol)
            audit.log_event("EXECUTION", f"REAL ORDER UNSUPPORTED: {signal.symbol}", "WARNING")

# Global Manager
execution_manager = ExecutionManager()
