from typing import Dict, List, Optional
from pydantic import BaseModel
import yaml
from antigravity.logging import get_logger

logger = get_logger("config")

class TrendConfig(BaseModel):
    enabled: bool = False
    name: str = "GoldenCross"
    fast_period: int = 50
    slow_period: int = 200
    risk_per_trade: float = 0.02

class MeanReversionConfig(BaseModel):
    enabled: bool = False
    name: str = "BollingerRSI"
    rsi_period: int = 14
    rsi_overbought: int = 70
    rsi_oversold: int = 30
    bb_period: int = 20
    bb_std: float = 2.0
    risk_per_trade: float = 0.02

class VolatilityConfig(BaseModel):
    enabled: bool = False
    name: str = "ATRBreakout"
    atr_period: int = 14
    multiplier: float = 3.0
    risk_per_trade: float = 0.02

class ScalpingConfig(BaseModel):
    enabled: bool = False
    name: str = "StochScalp"
    k_period: int = 14
    d_period: int = 3
    overbought: int = 80
    oversold: int = 20
    risk_per_trade: float = 0.01

class BBSqueezeConfig(BaseModel):
    enabled: bool = False
    name: str = "BBSqueeze"
    bb_period: int = 20
    bb_std: float = 2.0
    keltner_multiplier: float = 1.5
    momentum_period: int = 12
    risk_per_trade: float = 0.02

class GridConfig(BaseModel):
    enabled: bool = False
    name: str = "GridMaster"
    lower_price: float = 40000.0
    upper_price: float = 50000.0
    grid_levels: int = 10
    amount_per_grid: float = 0.001

class StrategiesConfig(BaseModel):
    trend_following: Optional[TrendConfig] = None
    mean_reversion: Optional[MeanReversionConfig] = None
    volatility_breakout: Optional[VolatilityConfig] = None
    scalping: Optional[ScalpingConfig] = None
    bb_squeeze: Optional[BBSqueezeConfig] = None
    grid: Optional[GridConfig] = None

def load_strategy_config(filepath: str = "strategies.yaml") -> StrategiesConfig:
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        # Mapping yaml keys to config structure
        config = StrategiesConfig(
            trend_following=TrendConfig(**data.get("strategies", {}).get("trend_following", {})),
            mean_reversion=MeanReversionConfig(**data.get("strategies", {}).get("mean_reversion", {})),
            volatility_breakout=VolatilityConfig(**data.get("strategies", {}).get("volatility_breakout", {})),
            scalping=ScalpingConfig(**data.get("strategies", {}).get("scalping", {})),
            bb_squeeze=BBSqueezeConfig(**data.get("strategies", {}).get("bb_squeeze", {})),
            grid=GridConfig(**data.get("strategies", {}).get("grid", {}))
        )
        return config
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        return StrategiesConfig()
