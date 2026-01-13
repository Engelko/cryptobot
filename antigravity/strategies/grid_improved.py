from typing import Optional, List, Dict
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent, OrderUpdateEvent
from antigravity.logging import get_logger

logger = get_logger("strategy_grid_improved")

class GridMasterImproved(BaseStrategy):
    """
    GridMasterImproved: A Grid Trading Strategy with dynamic range and validation.
    """
    VALID_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]

    def __init__(self, symbol: str, grid_levels: int = 10, amount_per_grid: float = 0.001):
        # Note: We pass [symbol] to BaseStrategy, but the class logic is single-symbol focused as per prompt
        super().__init__("GridMasterImproved", [symbol])
        self.symbol = symbol
        self.grid_levels = grid_levels
        self.amount_per_grid = amount_per_grid

        self.lower_price = 0.0
        self.upper_price = 0.0
        self.grid_prices = []
        self.active_orders = {} # {order_id: level_index}
        self.initialized = False

        # Validation on init
        self._validate_params()

    def _validate_params(self):
        if self.symbol not in self.VALID_SYMBOLS:
            raise ValueError(f"Invalid symbol: {self.symbol}. Must be one of {self.VALID_SYMBOLS}")
        if self.grid_levels > 100:
            raise ValueError(f"Grid levels {self.grid_levels} exceeds maximum of 100")
        if self.amount_per_grid <= 0:
            raise ValueError("Amount per grid must be positive")

    def set_dynamic_range(self, current_price: float, atr_value: float, sigma: float = 2.0):
        """
        Sets the grid range dynamically based on ATR.
        lower = current - sigma * atr
        upper = current + sigma * atr
        """
        if current_price <= 0 or atr_value <= 0:
            raise ValueError("Price and ATR must be positive")

        range_half = sigma * atr_value
        self.lower_price = current_price - range_half
        self.upper_price = current_price + range_half
        logger.info("grid_dynamic_range_set", symbol=self.symbol, lower=self.lower_price, upper=self.upper_price)

    def calculate_grid_prices(self) -> List[float]:
        """
        Calculates the price levels for the grid.
        Returns a list of prices from lower to upper.
        """
        if self.lower_price <= 0 or self.upper_price <= self.lower_price:
            raise ValueError("Invalid grid range. Set range using set_dynamic_range or manually first.")

        step = (self.upper_price - self.lower_price) / self.grid_levels
        # We want grid_levels intervals, so grid_levels + 1 lines?
        # Usually grid_levels implies the number of "zones" or "lines".
        # Prompt says: "Grid Levels = 10... [40000, 41111, ... 50000]" which is 10 intervals.
        self.grid_prices = [self.lower_price + (i * step) for i in range(self.grid_levels + 1)]
        return self.grid_prices

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        # Minimal implementation to satisfy BaseStrategy
        return None
