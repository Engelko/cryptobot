from typing import Optional, List, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent, OrderUpdateEvent
from antigravity.strategies.config import GridConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_grid_improved")

class GridMasterImproved(BaseStrategy):
    """
    GridMasterImproved: A Grid Trading Strategy with dynamic range and validation.
    """
    VALID_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]

    def __init__(self, config: GridConfig, symbols: List[str]):
        super().__init__("GridMasterImproved", symbols)
        self.config = config

        # Grid strategy typically works best on a single symbol per instance, or needs independent state per symbol.
        # BaseStrategy supports multiple symbols. We will maintain state per symbol.
        self.grid_levels = getattr(config, 'grid_levels', 10)
        self.amount_per_grid = getattr(config, 'amount_per_grid', 0.001)
        self.lower_price_config = getattr(config, 'lower_price', 0.0)
        self.upper_price_config = getattr(config, 'upper_price', 0.0)

        # State per symbol
        # {symbol: {"lower": float, "upper": float, "grid_prices": [], "active_orders": {}, "initialized": bool}}
        self.grid_states = {}
        for s in symbols:
            self.grid_states[s] = {
                "lower": self.lower_price_config,
                "upper": self.upper_price_config,
                "grid_prices": [],
                "active_orders": {}, # {order_id: level_index}
                "initialized": False,
                "pending_placements": [],
                "pending_counter_orders": []
            }

        self._validate_params()

    def _validate_params(self):
        for s in self.symbols:
             if s not in self.VALID_SYMBOLS:
                 # Warn but don't crash, user might want to trade other pairs
                 logger.warning("grid_symbol_warning", symbol=s, message="Symbol not in validated list")

        if self.grid_levels > 100:
             logger.warning("grid_levels_warning", levels=self.grid_levels, message="Levels exceed typical max")

        if self.amount_per_grid <= 0:
             raise ValueError("Amount per grid must be positive")

    def set_dynamic_range(self, symbol: str, current_price: float, atr_value: float, sigma: float = 2.0):
        """
        Sets the grid range dynamically based on ATR.
        """
        if symbol not in self.grid_states: return

        if current_price <= 0 or atr_value <= 0:
            return

        range_half = sigma * atr_value
        self.grid_states[symbol]["lower"] = current_price - range_half
        self.grid_states[symbol]["upper"] = current_price + range_half
        logger.info("grid_dynamic_range_set", symbol=symbol, lower=self.grid_states[symbol]["lower"], upper=self.grid_states[symbol]["upper"])

    def calculate_grid_prices(self, symbol: str) -> List[float]:
        """
        Calculates the price levels for the grid.
        """
        state = self.grid_states.get(symbol)
        if not state: return []

        lower = state["lower"]
        upper = state["upper"]

        if lower <= 0 or upper <= lower:
             return []

        step = (upper - lower) / self.grid_levels
        state["grid_prices"] = [lower + (i * step) for i in range(self.grid_levels + 1)]
        return state["grid_prices"]

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            symbol = event.symbol
            if symbol not in self.symbols: return None

            state = self.grid_states.get(symbol)
            if not state: return None

            # 0. Check Kill Switch
            kill_signal = await self._check_kill_switch(symbol, event.close, state)
            if kill_signal:
                return kill_signal

            # 1. Check Counter Orders (Priority)
            if state["pending_counter_orders"]:
                order = state["pending_counter_orders"].pop(0)
                await self.save_state() # Persist state update

                side_enum = SignalType(order["side"])
                return Signal(side_enum, symbol, order["price"], quantity=self.amount_per_grid, reason=order["reason"])

            # 2. Initialize
            if not state["initialized"]:
                # If range is not set effectively (0.0 default), try to use current price + hardcoded spread if not dynamic
                # Or require user to set it. Config usually has defaults.
                if state["lower"] <= 0 or state["upper"] <= 0:
                     # Auto-set range around current price if config was invalid/zero
                     # Assume 10% range
                     state["lower"] = event.close * 0.95
                     state["upper"] = event.close * 1.05
                     logger.info("grid_auto_range", symbol=symbol, lower=state["lower"], upper=state["upper"])

                if state["lower"] <= event.close <= state["upper"]:
                     logger.info("grid_initializing", symbol=symbol, price=event.close)
                     self.calculate_grid_prices(symbol)
                     state["pending_placements"] = [i for i in range(len(state["grid_prices"]))]
                     state["initialized"] = True
                     await self.save_state()
                return None

            # 3. Process Pending Placements (Init)
            if state["pending_placements"]:
                idx = state["pending_placements"][0]
                prices = state["grid_prices"]
                if not prices: return None

                level_price = prices[idx]

                # Simple Logic: Place limit orders.
                # Since we return Signal(BUY/SELL), the Execution engine executes it.
                # Ideally, we want LIMIT orders. Signal has `price`. Execution engine should handle Limit if price is specified.
                # We need to determine SIDE.
                # Below current price -> BUY. Above -> SELL.

                side = None
                if level_price < event.close:
                    side = SignalType.BUY
                else:
                    side = SignalType.SELL

                # Pop it
                state["pending_placements"].pop(0)

                return Signal(side, symbol, level_price, quantity=self.amount_per_grid, reason=f"Grid Init {idx}")

        return None

    async def on_order_update(self, event: OrderUpdateEvent):
        symbol = event.symbol
        if symbol not in self.symbols: return

        state = self.grid_states.get(symbol)
        if not state or not state["initialized"]: return

        prices = state["grid_prices"]
        if not prices: return

        if event.order_status == "New":
            # Map order to grid level
            closest_idx = -1
            min_diff = float("inf")
            for i, p in enumerate(prices):
                diff = abs(p - event.price)
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i

            # If close enough (within 10% of step size)
            step = (state["upper"] - state["lower"]) / self.grid_levels
            if min_diff < step * 0.2:
                state["active_orders"][event.order_id] = closest_idx
                logger.info("grid_order_tracked", order_id=event.order_id, level_idx=closest_idx)
                await self.save_state()

        elif event.order_status == "Filled":
            if event.order_id in state["active_orders"]:
                idx = state["active_orders"].pop(event.order_id)
                logger.info("grid_level_filled", level_idx=idx, side=event.side)

                target_idx = -1
                side = SignalType.HOLD

                # If we Bought at X, we want to Sell at X+1
                if event.side.upper() == "BUY":
                    target_idx = idx + 1
                    side = SignalType.SELL
                # If we Sold at Y, we want to Buy at Y-1
                else:
                    target_idx = idx - 1
                    side = SignalType.BUY

                if 0 <= target_idx < len(prices):
                    target_price = prices[target_idx]
                    state["pending_counter_orders"].append({
                        "side": side.value,
                        "price": target_price,
                        "reason": f"Grid Flip from {idx}"
                    })

                await self.save_state()

    async def _check_kill_switch(self, symbol: str, current_price: float, state: Dict) -> Optional[Signal]:
        """
        Stop Loss / Kill Switch for Grid.
        If price moves significantly outside the grid, close all positions to prevent liquidation/deep bags.
        """
        # Buffer: 5% outside range
        lower_limit = state["lower"] * 0.95
        upper_limit = state["upper"] * 1.05

        # If price drops below lower limit (Holding Longs in falling market)
        if current_price < lower_limit:
            logger.warning("grid_kill_switch_triggered", symbol=symbol, price=current_price, limit=lower_limit, reason="Price below grid")
            # Signal SELL to close everything (assuming execution manager handles "SELL" as "Close Long")
            # We reset state to stop grid
            state["initialized"] = False
            state["active_orders"] = {}
            state["pending_placements"] = []
            state["pending_counter_orders"] = []
            await self.save_state()
            return Signal(SignalType.SELL, symbol, quantity=None, reason="Grid Kill Switch (Low)")

        # If price goes above upper limit (Holding Shorts in rising market - only relevant for Futures Grid)
        # Our current implementation is Spot-like (Long Only logic mostly), but signals can be short.
        # If we are in Futures mode, we might have Short positions from upper grid levels?
        # The current implementation sends SELL signals at upper levels. In Spot, that's selling asset. In Futures, that's Opening Short?
        # The logic: "If we Bought at X, we Sell at X+1". This implies Closing Longs.
        # So we are Long Only?
        # "If we Sold at Y, we want to Buy at Y-1".
        # This implies we are oscillating.

        # Safe Kill Switch: If price > upper_limit, we should ensure we have no Short exposure.
        # Since we likely just sold everything on the way up, we are likely flat or holding small shorts if we entered shorts.
        # Assuming Long-Only Grid for now: No risk on upside (just Sold out).

        return None
