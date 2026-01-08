from typing import Optional, List, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent, OrderUpdateEvent
from antigravity.strategies.config import GridConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_grid")

class GridStrategy(BaseStrategy):
    def __init__(self, config: GridConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        # State structure:
        # {
        #   "symbol": {
        #      "levels": [price1, price2, ...],
        #      "active_orders": { "order_id": index_in_levels },
        #      "initialized": bool
        #   }
        # }

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            symbol = event.symbol
            if symbol not in self.symbols: return None

            state = self.state.get(symbol, {})

            # 0. Check Counter Orders (Priority)
            pending_counter = state.get("pending_counter_orders", [])
            if pending_counter:
                order = pending_counter.pop(0)
                await self.save_state()
                side_enum = SignalType(order["side"])
                return Signal(side_enum, symbol, order["price"], quantity=self.config.amount_per_grid, reason=order["reason"])

            # 1. Initialize
            if not state.get("initialized"):
                 if self.config.lower_price <= event.close <= self.config.upper_price:
                     logger.info("grid_initializing", symbol=symbol, price=event.close)
                     await self._initialize_grid(symbol, event.close)
                 return None

            # 2. Process Pending Placements (Init)
            pending_init = state.get("pending_placements", [])
            if pending_init:
                idx = pending_init[0]
                levels = state["levels"]
                level_price = levels[idx]

                if level_price < event.close * 0.999:
                    state["pending_placements"].pop(0)
                    return Signal(SignalType.BUY, symbol, level_price, quantity=self.config.amount_per_grid, reason=f"Grid Init {idx}")
                elif level_price > event.close * 1.001:
                    state["pending_placements"].pop(0)
                    return Signal(SignalType.SELL, symbol, level_price, quantity=self.config.amount_per_grid, reason=f"Grid Init {idx}")
                else:
                    state["pending_placements"].pop(0)
                    return None

        return None

    async def _initialize_grid(self, symbol: str, current_price: float):
        step = (self.config.upper_price - self.config.lower_price) / self.config.grid_levels
        levels = [self.config.lower_price + (i * step) for i in range(self.config.grid_levels + 1)]

        self.state[symbol] = {
            "levels": levels,
            "active_orders": {},
            "initialized": True,
            "pending_placements": [i for i in range(len(levels))]
        }
        await self.save_state()

    async def on_order_update(self, event: OrderUpdateEvent):
        symbol = event.symbol
        if symbol not in self.symbols: return

        levels = self.state[symbol].get("levels", [])
        if not levels: return

        if event.order_status == "New":
            closest_idx = -1
            min_diff = float("inf")
            for i, lvl in enumerate(levels):
                diff = abs(lvl - event.price)
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = i

            if min_diff < (levels[1] - levels[0]) * 0.1:
                self.state[symbol]["active_orders"][event.order_id] = closest_idx
                logger.info("grid_order_tracked", order_id=event.order_id, level_idx=closest_idx)
                await self.save_state()

        elif event.order_status == "Filled":
            if event.order_id in self.state[symbol]["active_orders"]:
                idx = self.state[symbol]["active_orders"].pop(event.order_id)
                logger.info("grid_level_filled", level_idx=idx, side=event.side)

                target_idx = -1
                side = SignalType.HOLD

                if event.side.upper() == "BUY":
                    target_idx = idx + 1
                    side = SignalType.SELL
                else:
                    target_idx = idx - 1
                    side = SignalType.BUY

                if 0 <= target_idx < len(levels):
                    target_price = levels[target_idx]
                    self.state[symbol].setdefault("pending_counter_orders", []).append({
                        "side": side.value,
                        "price": target_price,
                        "reason": f"Grid Flip from {idx}"
                    })

                await self.save_state()
