from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timezone
from enum import Enum
import json

class TradeResult(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"

@dataclass
class Trade:
    id: str
    symbol: str
    entry_type: str  # A, B, C
    signal_type: str  # BUY, SELL
    entry_price: float
    entry_time: datetime
    quantity: float
    leverage: float
    stop_loss: float
    take_profit_levels: List[Dict] = field(default_factory=list)
    
    # Filled during close
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    result: Optional[TradeResult] = None
    pnl: Optional[float] = None
    pnl_percentage: Optional[float] = None
    fees_paid: float = 0.0
    
    # Partial exits
    partial_exits: List[Dict] = field(default_factory=list)
    remaining_quantity: Optional[float] = None

@dataclass
class DailyStats:
    date: datetime
    trades_total: int = 0
    trades_winning: int = 0
    trades_losing: int = 0
    trades_breakeven: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    max_drawdown: float = 0.0
    max_profit: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    
    def calculate_metrics(self):
        """Calculate performance metrics"""
        if self.trades_total > 0:
            self.win_rate = (self.trades_winning / self.trades_total) * 100
        
        # Calculate profit factor
        winning_pnl = sum(abs(trade.pnl) for trade in self.get_winning_trades())
        losing_pnl = sum(abs(trade.pnl) for trade in self.get_losing_trades())
        
        if losing_pnl > 0:
            self.profit_factor = winning_pnl / losing_pnl
        elif winning_pnl > 0:
            self.profit_factor = float('inf')
        else:
            self.profit_factor = 0.0
    
    def get_winning_trades(self) -> List[Trade]:
        """Get list of winning trades"""
        return [trade for trade in getattr(self, '_trades', []) if trade.result == TradeResult.WIN]
    
    def get_losing_trades(self) -> List[Trade]:
        """Get list of losing trades"""
        return [trade for trade in getattr(self, '_trades', []) if trade.result == TradeResult.LOSS]

class PerformanceTracker:
    def __init__(self):
        self.trades: Dict[str, Trade] = {}
        self.daily_stats: Dict[str, DailyStats] = {}
        self.current_positions: Dict[str, Trade] = {}
        self.total_trades = 0
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.max_consecutive_losses = 0
        self.max_consecutive_wins = 0
        self.daily_loss_limit_hit = False
        self.last_reset_date = None

    def add_trade(self, trade: Trade) -> str:
        """Add a new trade to the tracker"""
        trade_id = trade.id
        self.trades[trade_id] = trade
        self.current_positions[trade.symbol] = trade
        self.total_trades += 1
        
        # Set remaining quantity
        trade.remaining_quantity = trade.quantity
        
        # Update daily stats
        self._update_daily_stats_for_entry(trade)
        
        return trade_id

    def close_trade(self, trade_id: str, exit_price: float, exit_time: datetime = None) -> Optional[Trade]:
        """Close a trade and calculate results"""
        if trade_id not in self.trades:
            return None
        
        trade = self.trades[trade_id]
        if trade.exit_price is not None:
            return trade  # Already closed
        
        # Set exit details
        trade.exit_price = exit_price
        trade.exit_time = exit_time or datetime.now(timezone.utc)
        
        # Calculate PnL
        if trade.signal_type == "BUY":
            price_change = exit_price - trade.entry_price
        else:  # SELL
            price_change = trade.entry_price - exit_price
        
        # Apply leverage
        gross_pnl = price_change * trade.quantity * trade.leverage
        trade.fees_paid = self._estimate_fees(trade.entry_price, exit_price, trade.quantity)
        trade.pnl = gross_pnl - trade.fees_paid
        
        # Calculate percentage
        if trade.signal_type == "BUY":
            trade.pnl_percentage = (price_change / trade.entry_price) * trade.leverage * 100
        else:
            trade.pnl_percentage = (price_change / trade.entry_price) * trade.leverage * 100
        
        # Determine result
        if trade.pnl > 0:
            trade.result = TradeResult.WIN
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
        elif trade.pnl < 0:
            trade.result = TradeResult.LOSS
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
        else:
            trade.result = TradeResult.BREAKEVEN
            self.consecutive_losses = 0
            self.consecutive_wins = 0
        
        # Update totals
        self.total_pnl += trade.pnl
        self.total_fees += trade.fees_paid
        
        # Remove from current positions
        if trade.symbol in self.current_positions:
            del self.current_positions[trade.symbol]
        
        # Update daily stats
        self._update_daily_stats_for_exit(trade)
        
        return trade

    def add_partial_exit(self, trade_id: str, exit_price: float, quantity_percentage: float, 
                        exit_time: datetime = None) -> Optional[Dict]:
        """Add a partial exit to a trade"""
        if trade_id not in self.trades:
            return None
        
        trade = self.trades[trade_id]
        exit_quantity = trade.quantity * quantity_percentage
        
        # Calculate PnL for this partial exit
        if trade.signal_type == "BUY":
            price_change = exit_price - trade.entry_price
        else:  # SELL
            price_change = trade.entry_price - exit_price
        
        partial_pnl = price_change * exit_quantity * trade.leverage
        partial_fees = self._estimate_fees(trade.entry_price, exit_price, exit_quantity)
        net_partial_pnl = partial_pnl - partial_fees
        
        # Add to partial exits
        partial_exit = {
            "exit_time": exit_time or datetime.now(timezone.utc),
            "exit_price": exit_price,
            "quantity_percentage": quantity_percentage,
            "exit_quantity": exit_quantity,
            "pnl": net_partial_pnl,
            "fees": partial_fees
        }
        
        trade.partial_exits.append(partial_exit)
        trade.remaining_quantity -= exit_quantity
        trade.pnl = (trade.pnl or 0) + net_partial_pnl
        trade.fees_paid += partial_fees
        
        # Update totals
        self.total_pnl += net_partial_pnl
        self.total_fees += partial_fees
        
        # Check if position is fully closed
        if trade.remaining_quantity <= 0:
            trade.exit_time = partial_exit["exit_time"]
            if trade.pnl > 0:
                trade.result = TradeResult.WIN
            elif trade.pnl < 0:
                trade.result = TradeResult.LOSS
            else:
                trade.result = TradeResult.BREAKEVEN
            
            # Remove from current positions
            if trade.symbol in self.current_positions:
                del self.current_positions[trade.symbol]
        
        return partial_exit

    def get_daily_stats(self, date: datetime = None) -> Optional[DailyStats]:
        """Get statistics for a specific date"""
        if date is None:
            date = datetime.now(timezone.utc)
        
        date_str = date.strftime("%Y-%m-%d")
        return self.daily_stats.get(date_str)

    def get_win_rate(self, days: int = 30) -> float:
        """Get win rate for last N days"""
        recent_trades = self.get_recent_trades(days)
        if not recent_trades:
            return 0.0
        
        winning_trades = [t for t in recent_trades if t.result == TradeResult.WIN]
        return len(winning_trades) / len(recent_trades) * 100

    def get_profit_factor(self, days: int = 30) -> float:
        """Get profit factor for last N days"""
        recent_trades = self.get_recent_trades(days)
        if not recent_trades:
            return 0.0
        
        winning_pnl = sum(t.pnl for t in recent_trades if t.result == TradeResult.WIN and t.pnl)
        losing_pnl = sum(abs(t.pnl) for t in recent_trades if t.result == TradeResult.LOSS and t.pnl)
        
        return winning_pnl / losing_pnl if losing_pnl > 0 else (float('inf') if winning_pnl > 0 else 0.0)

    def get_average_win_loss_ratio(self, days: int = 30) -> float:
        """Get average win to loss ratio for last N days"""
        recent_trades = self.get_recent_trades(days)
        if not recent_trades:
            return 0.0
        
        winning_trades = [t for t in recent_trades if t.result == TradeResult.WIN and t.pnl]
        losing_trades = [t for t in recent_trades if t.result == TradeResult.LOSS and t.pnl]
        
        if not winning_trades or not losing_trades:
            return 0.0
        
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades)
        avg_loss = sum(abs(t.pnl) for t in losing_trades) / len(losing_trades)
        
        return avg_win / avg_loss if avg_loss > 0 else 0.0

    def get_max_drawdown(self, days: int = 30) -> float:
        """Get maximum drawdown for last N days"""
        recent_trades = self.get_recent_trades(days)
        if not recent_trades:
            return 0.0
        
        cumulative_pnl = 0.0
        peak = 0.0
        max_drawdown = 0.0
        
        for trade in sorted(recent_trades, key=lambda x: x.exit_time or trade.entry_time):
            if trade.pnl:
                cumulative_pnl += trade.pnl
                peak = max(peak, cumulative_pnl)
                drawdown = peak - cumulative_pnl
                max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown

    def get_recent_trades(self, days: int = 30) -> List[Trade]:
        """Get trades from last N days"""
        cutoff_date = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)
        cutoff_datetime = datetime.fromtimestamp(cutoff_date, timezone.utc)
        
        return [trade for trade in self.trades.values() 
                if (trade.exit_time or trade.entry_time) >= cutoff_datetime]

    def get_entry_type_stats(self) -> Dict[str, Dict]:
        """Get statistics by entry type (A, B, C)"""
        stats = {"A": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0},
                "B": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0},
                "C": {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}}
        
        for trade in self.trades.values():
            if trade.entry_type in stats:
                stats[trade.entry_type]["total"] += 1
                stats[trade.entry_type]["pnl"] += trade.pnl or 0.0
                
                if trade.result == TradeResult.WIN:
                    stats[trade.entry_type]["wins"] += 1
                elif trade.result == TradeResult.LOSS:
                    stats[trade.entry_type]["losses"] += 1
        
        return stats

    def _update_daily_stats_for_entry(self, trade: Trade):
        """Update daily statistics when trade is opened"""
        date_str = trade.entry_time.strftime("%Y-%m-%d")
        
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = DailyStats(
                date=datetime.combine(trade.entry_time.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
            )
        
        self.daily_stats[date_str].trades_total += 1

    def _update_daily_stats_for_exit(self, trade: Trade):
        """Update daily statistics when trade is closed"""
        date_str = trade.exit_time.strftime("%Y-%m-%d")
        
        if date_str not in self.daily_stats:
            self.daily_stats[date_str] = DailyStats(
                date=datetime.combine(trade.exit_time.date(), datetime.min.time()).replace(tzinfo=timezone.utc)
            )
        
        stats = self.daily_stats[date_str]
        
        if trade.result == TradeResult.WIN:
            stats.trades_winning += 1
        elif trade.result == TradeResult.LOSS:
            stats.trades_losing += 1
        else:
            stats.trades_breakeven += 1
        
        stats.total_pnl += trade.pnl or 0.0
        stats.total_fees += trade.fees_paid
        
        # Calculate metrics
        stats.calculate_metrics()

    def _estimate_fees(self, entry_price: float, exit_price: float, quantity: float) -> float:
        """Estimate trading fees (default 0.1% per trade)"""
        # Bybit maker fee: 0.1%, taker fee: 0.1%
        fee_rate = 0.001
        return (entry_price + exit_price) * quantity * fee_rate

    def check_daily_loss_limit(self, daily_loss_limit: float, current_date: datetime = None) -> bool:
        """Check if daily loss limit has been hit"""
        if current_date is None:
            current_date = datetime.now(timezone.utc)
        
        date_str = current_date.strftime("%Y-%m-%d")
        if date_str not in self.daily_stats:
            return False
        
        daily_loss = abs(min(0, self.daily_stats[date_str].total_pnl))
        initial_balance = 1000.0  # This should come from account
        loss_percentage = daily_loss / initial_balance
        
        return loss_percentage >= daily_loss_limit

    def get_summary_report(self) -> Dict:
        """Get comprehensive performance summary"""
        closed_trades = [t for t in self.trades.values() if t.result]
        
        if not closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "total_pnl": 0,
                "average_win_loss_ratio": 0
            }
        
        total_wins = len([t for t in closed_trades if t.result == TradeResult.WIN])
        total_losses = len([t for t in closed_trades if t.result == TradeResult.LOSS])
        
        winning_pnl = sum(t.pnl for t in closed_trades if t.result == TradeResult.WIN and t.pnl)
        losing_pnl = sum(abs(t.pnl) for t in closed_trades if t.result == TradeResult.LOSS and t.pnl)
        
        avg_win = winning_pnl / total_wins if total_wins > 0 else 0
        avg_loss = losing_pnl / total_losses if total_losses > 0 else 0
        
        return {
            "total_trades": len(closed_trades),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_breakeven": len([t for t in closed_trades if t.result == TradeResult.BREAKEVEN]),
            "win_rate": (total_wins / len(closed_trades)) * 100 if closed_trades else 0,
            "profit_factor": winning_pnl / losing_pnl if losing_pnl > 0 else (float('inf') if winning_pnl > 0 else 0),
            "total_pnl": self.total_pnl,
            "total_fees": self.total_fees,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "average_win_loss_ratio": avg_win / avg_loss if avg_loss > 0 else 0,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_positions": len(self.current_positions),
            "entry_type_stats": self.get_entry_type_stats()
        }