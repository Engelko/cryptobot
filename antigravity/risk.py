import time
from datetime import datetime, timezone
from antigravity.config import settings
from antigravity.strategy import Signal, SignalType
from antigravity.logging import get_logger
from antigravity.client import BybitClient
from antigravity.execution import execution_manager
from antigravity.database import db
from antigravity.event import event_bus, TradeClosedEvent, on_event
from antigravity.metrics import metrics
from antigravity.fees import FeeConfig

logger = get_logger("risk_manager")

# Minimum order cost in USDT (approximate)
MIN_ORDER_COST = 10.0

class RiskManager:
    def __init__(self):
        self.max_daily_loss = settings.MAX_DAILY_LOSS
        self.max_position_size = settings.MAX_POSITION_SIZE
        self.current_daily_loss = 0.0
        self.last_reset_date = None

        # Cache fields
        self._cached_balance = 0.0
        self._balance_cache_time = 0
        self._last_rejection_reason = None

        # Load persisted state
        state = db.get_risk_state()
        if state:
            # Handle SQLAlchemy object or dict
            if hasattr(state, "daily_loss"):
                self.current_daily_loss = state.daily_loss
                self.last_reset_date = state.last_reset_date
            else:
                self.current_daily_loss = state["daily_loss"]
                self.last_reset_date = state["last_reset_date"]

        # Subscribe to trade closed events
        event_bus.subscribe(TradeClosedEvent, self._handle_trade_closed)

    def _get_current_utc_date(self) -> str:
        """Returns current UTC date in YYYY-MM-DD format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_reset(self):
        """Resets daily loss if the date has changed (UTC)."""
        current_date = self._get_current_utc_date()

        if self.last_reset_date != current_date:
            logger.info("risk_daily_reset", old_date=self.last_reset_date, new_date=current_date, previous_loss=self.current_daily_loss)
            self.current_daily_loss = 0.0
            self.last_reset_date = current_date
            # Persist reset state
            db.update_risk_state(self.current_daily_loss, self.last_reset_date)

    async def _handle_trade_closed(self, event: TradeClosedEvent):
        """Event handler for closed trades."""
        self.update_metrics(event.pnl)

    async def check_signal(self, signal: Signal) -> bool:
        """
        Validate if the signal matches risk parameters.
        Returns True if safe, False if blocked.
        """
        # 0. Check Reset
        self._check_reset()

        # Check existing positions to allow "Reduce Only" trades
        # If we are closing a position, we should usually allow it regardless of limits
        is_reduce_only = False
        try:
            # We need to check actual exchange position to know if this reduces exposure.
            # This is a bit heavy for RiskManager, but necessary for correctness.
            # We assume RealBroker mode here mostly.
            if not settings.SIMULATION_MODE:
                client = BybitClient()
                try:
                    positions = await client.get_positions(category="linear", symbol=signal.symbol)
                    for p in positions:
                        size = float(p.get("size", 0))
                        side = p.get("side")
                        if size > 0:
                            # If we have Long and signal is SELL -> Reduce
                            if side == "Buy" and signal.type == SignalType.SELL:
                                is_reduce_only = True
                            # If we have Short and signal is BUY -> Reduce
                            elif side == "Sell" and signal.type == SignalType.BUY:
                                is_reduce_only = True
                finally:
                    await client.close()
        except Exception as e:
            logger.warning("risk_position_check_failed", error=str(e))

        if is_reduce_only:
            logger.info("risk_reduce_only_bypass", symbol=signal.symbol, type=signal.type)
            return True

        # 1. Check Daily Loss Limit
        if self.current_daily_loss >= self.max_daily_loss:
            logger.warning("risk_block", reason="daily_loss_limit_exceeded", 
                           current_loss=self.current_daily_loss, limit=self.max_daily_loss)
            return False

        # 2. Check Fees vs Edge (Basic)
        # We don't have expected edge in signal yet, but we can ensure notional is high enough that fees don't eat it all.
        # This is implicitly covered by MIN_ORDER_COST but let's be explicit if needed.
        # For now, relying on MIN_ORDER_COST is enough for fees.

        # 3. Check Position Size
        # If quantity is provided, we check against MAX_POSITION_SIZE and Available Balance.
        # If quantity is NOT provided, we check if we have minimum balance to execute ANY trade.

        available_balance = await self._get_available_balance()

        if signal.quantity and signal.price:
            notional = signal.quantity * signal.price

            # Check Max Position Size Config
            if notional > self.max_position_size:
                logger.warning("risk_block", reason="max_position_size_exceeded", 
                               notional=notional, limit=self.max_position_size)
                return False

            # Check Account Balance (considering leverage)
            # If leverage is provided, we check MARGIN required, not full notional.
            leverage = signal.leverage if signal.leverage and signal.leverage > 0 else 1.0

            # Fee Buffer: Reserve 1% for fees/slippage
            balance_for_trading = available_balance * 0.99

            margin_required = notional / leverage

            if margin_required > balance_for_trading:
                 # Instead of rejecting, we resize the signal to match available balance
                 # Max Notional = Balance * Leverage
                 max_notional_allowed = balance_for_trading * leverage

                 # Recalculate quantity
                 new_quantity = max_notional_allowed / signal.price

                 # Check if the new quantity is still viable (above min cost)
                 new_notional = new_quantity * signal.price
                 if new_notional < MIN_ORDER_COST:
                     logger.warning("risk_block", reason="insufficient_balance_for_min_order",
                                    required_margin=margin_required, available=available_balance,
                                    min_order_cost=MIN_ORDER_COST)
                     return False

                 # Update signal in place
                 logger.info("risk_resize",
                             original_qty=signal.quantity,
                             new_qty=new_quantity,
                             reason="insufficient_balance_margin_limit",
                             available_balance=balance_for_trading,
                             leverage=leverage)

                 signal.quantity = new_quantity
                 # Signal is now safe to proceed

        else:
            # Quantity not provided. Strategy relies on Execution logic to size the trade.
            # Execution logic uses min(balance, max_position_size).
            # We must ensure we have at least enough balance for a minimum order (approx $10).
            executable_size = min(available_balance, self.max_position_size)

            if executable_size < MIN_ORDER_COST:
                logger.warning("risk_block", reason="insufficient_balance_for_min_order",
                               available=available_balance, max_pos=self.max_position_size,
                               executable=executable_size, min_required=MIN_ORDER_COST)
                return False

        return True

    def update_metrics(self, realized_pnl: float):
        """
        Update risk metrics after a trade closes.
        """
        # Ensure we are in the correct day bucket before adding loss
        self._check_reset()

        if realized_pnl < 0:
            loss = abs(realized_pnl)
            self.current_daily_loss += loss
            logger.info("risk_loss_updated", added_loss=loss, total_daily_loss=self.current_daily_loss)

            # Persist new loss state
            db.update_risk_state(self.current_daily_loss, self.last_reset_date)

    
    async def _fetch_balance_from_api(self) -> float:
        """Fetch fresh balance from API"""
        if settings.SIMULATION_MODE:
            return execution_manager.paper_broker.balance
        
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            if "totalWalletBalance" in balance_data:
                return float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))
        finally:
            await client.close()
        
        return 0.0


    async def _get_available_balance(self) -> float:
        """
        Fetch available USDT balance.
        If Simulation Mode, fetch from PaperBroker.
        If Real Mode, fetch from Bybit API.
        """
        if settings.SIMULATION_MODE:
            return execution_manager.paper_broker.balance

        # Real Mode
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            # Logic similar to RealBroker._parse_available_balance
            if "totalWalletBalance" in balance_data:
                 return float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))
        except Exception as e:
            logger.error("risk_balance_fetch_error", error=str(e))
        finally:
            await client.close()

        return 0.0
