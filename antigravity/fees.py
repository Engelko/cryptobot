from typing import Dict, Optional, Literal
from dataclasses import dataclass
from antigravity.config import settings

MarketType = Literal["spot", "linear"]

@dataclass
class FeeSchedule:
    maker: float
    taker: float

class FeeConfig:
    # Defaults based on Bybit Standard Fees (Non-VIP)
    # Spot: 0.1% Maker / 0.1% Taker
    # Linear Futures: 0.02% Maker / 0.055% Taker

    DEFAULTS = {
        "spot": FeeSchedule(maker=0.001, taker=0.001),
        "linear": FeeSchedule(maker=0.0002, taker=0.00055)
    }

    @staticmethod
    def get_fees(market_type: MarketType) -> FeeSchedule:
        # Potentially load from config/env in future
        return FeeConfig.DEFAULTS.get(market_type, FeeConfig.DEFAULTS["linear"])

    @staticmethod
    def estimate_fee(qty: float, price: float, market_type: MarketType, is_maker: bool = False) -> float:
        fees = FeeConfig.get_fees(market_type)
        rate = fees.maker if is_maker else fees.taker
        return qty * price * rate
