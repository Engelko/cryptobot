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
    leverage: float = 1.0

class MeanReversionConfig(BaseModel):
    enabled: bool = False
    name: str = "BollingerRSI"
    rsi_period: int = 14
    rsi_overbought: int = 70
    rsi_oversold: int = 30
    bb_period: int = 20
    bb_std: float = 2.0
    risk_per_trade: float = 0.02
    leverage: float = 1.0

class VolatilityConfig(BaseModel):
    enabled: bool = False
    name: str = "ATRBreakout"
    atr_period: int = 14
    multiplier: float = 3.0
    risk_per_trade: float = 0.02
    leverage: float = 1.0

class ScalpingConfig(BaseModel):
    enabled: bool = False
    name: str = "StochScalp"
    k_period: int = 14
    d_period: int = 3
    overbought: int = 80
    oversold: int = 20
    risk_per_trade: float = 0.01
    leverage: float = 1.0

class BBSqueezeConfig(BaseModel):
    enabled: bool = False
    name: str = "BBSqueeze"
    bb_period: int = 20
    bb_std: float = 2.0
    keltner_multiplier: float = 1.5
    momentum_period: int = 12
    risk_per_trade: float = 0.02
    leverage: float = 1.0

class GridConfig(BaseModel):
    enabled: bool = False
    name: str = "GridMaster"
    lower_price: float = 40000.0
    upper_price: float = 50000.0
    grid_levels: int = 10
    amount_per_grid: float = 0.001
    leverage: float = 1.0

class DynamicRiskLeverageConfig(BaseModel):
    enabled: bool = False
    name: str = "DynamicRiskLeverage"
    
    # Timeframes
    macro_tf: str = "4h"  # For trend analysis
    main_tf: str = "1h"  # For entry signals
    
    # Risk parameters
    max_risk_per_trade: float = 0.02  # 2% max
    daily_loss_limit: float = 0.05    # 5% daily max
    
    # Leverage tiers
    high_risk_leverage: float = 2.5   # x2-x3
    medium_risk_leverage: float = 6.0 # x5-x7
    low_risk_leverage: float = 9.0    # x8-x10
    extreme_risk_leverage: float = 12.5 # x10-x15
    
    # Entry types risk allocation
    type_a_risk: float = 0.015  # 1.5-2%
    type_b_risk: float = 0.012  # 1-1.5%
    type_c_risk: float = 0.005  # 0.5%
    
    # Technical indicators
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    volume_ma_period: int = 20
    
    # Levels and zones
    support_resistance_lookback: int = 100
    min_distance_to_level: float = 0.015  # 1.5%
    max_distance_to_level: float = 0.03   # 3%
    
    # Volume filters
    min_volume_multiplier: float = 1.3
    max_volume_drop_threshold: float = 0.7  # 30% below average
    
    # RSI zones
    rsi_extreme_oversold: float = 20
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    rsi_extreme_overbought: float = 80

class StrategiesConfig(BaseModel):
    trend_following: Optional[TrendConfig] = None
    mean_reversion: Optional[MeanReversionConfig] = None
    volatility_breakout: Optional[VolatilityConfig] = None
    scalping: Optional[ScalpingConfig] = None
    bb_squeeze: Optional[BBSqueezeConfig] = None
    grid: Optional[GridConfig] = None
    dynamic_risk_leverage: Optional[DynamicRiskLeverageConfig] = None

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
            grid=GridConfig(**data.get("strategies", {}).get("grid", {})),
            dynamic_risk_leverage=DynamicRiskLeverageConfig(**data.get("strategies", {}).get("dynamic_risk_leverage", {}))
        )
        return config
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        return StrategiesConfig()
