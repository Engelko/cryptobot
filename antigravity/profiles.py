import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from antigravity.logging import get_logger

logger = get_logger("profiles")

@dataclass
class TradingProfile:
    name: str
    description: str
    is_testnet: bool
    
    max_spread: float
    max_leverage: float
    max_daily_loss: float
    max_position_size: float
    max_single_trade_loss: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_trigger: float
    min_hold_time: int
    cooldown_after_loss: int
    
    session_blacklist: list
    min_adx_entry: float
    max_atr_pct: float
    
    enable_spread_check: bool
    spread_multiplier: float
    enable_spot_mode_for_volatile: bool
    enable_regime_filter: bool
    
    risk_per_trade: float

PROFILES: Dict[str, TradingProfile] = {
    "testnet": TradingProfile(
        name="Testnet",
        description="Для тестирования на Bybit Testnet. Ослабленные фильтры, больший спред.",
        is_testnet=True,
        
        max_spread=0.10,
        max_leverage=2.0,
        max_daily_loss=100.0,
        max_position_size=100.0,
        max_single_trade_loss=30.0,
        stop_loss_pct=0.03,
        take_profit_pct=0.04,
        trailing_stop_trigger=0.03,
        min_hold_time=30,
        cooldown_after_loss=300,
        
        session_blacklist=[],
        min_adx_entry=15.0,
        max_atr_pct=0.10,
        
        enable_spread_check=True,
        spread_multiplier=10.0,
        enable_spot_mode_for_volatile=False,
        enable_regime_filter=False,
        
        risk_per_trade=0.02
    ),
    
    "mainnet_conservative": TradingProfile(
        name="Mainnet Conservative",
        description="Для реальной торговли с минимальным риском. Строгие фильтры.",
        is_testnet=False,
        
        max_spread=0.001,
        max_leverage=1.5,
        max_daily_loss=20.0,
        max_position_size=30.0,
        max_single_trade_loss=10.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.03,
        trailing_stop_trigger=0.025,
        min_hold_time=60,
        cooldown_after_loss=900,
        
        session_blacklist=[16, 17, 18, 19, 20, 21, 22, 23],
        min_adx_entry=25.0,
        max_atr_pct=0.05,
        
        enable_spread_check=True,
        spread_multiplier=1.0,
        enable_spot_mode_for_volatile=True,
        enable_regime_filter=True,
        
        risk_per_trade=0.01
    ),
    
    "mainnet_aggressive": TradingProfile(
        name="Mainnet Aggressive",
        description="Для реальной торговли с повышенным риском. Больше сделок.",
        is_testnet=False,
        
        max_spread=0.002,
        max_leverage=3.0,
        max_daily_loss=50.0,
        max_position_size=75.0,
        max_single_trade_loss=20.0,
        stop_loss_pct=0.025,
        take_profit_pct=0.04,
        trailing_stop_trigger=0.03,
        min_hold_time=45,
        cooldown_after_loss=600,
        
        session_blacklist=[18, 19, 20, 21],
        min_adx_entry=20.0,
        max_atr_pct=0.07,
        
        enable_spread_check=True,
        spread_multiplier=1.0,
        enable_spot_mode_for_volatile=True,
        enable_regime_filter=True,
        
        risk_per_trade=0.015
    )
}

PROFILE_FILE = "storage/current_profile.json"

_current_profile: Optional[TradingProfile] = None

def get_current_profile() -> TradingProfile:
    global _current_profile
    if _current_profile is None:
        _current_profile = load_profile()
    return _current_profile

def load_profile() -> TradingProfile:
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r") as f:
                data = json.load(f)
                profile_name = data.get("profile", "testnet")
                if profile_name in PROFILES:
                    logger.info("profile_loaded", profile=profile_name)
                    return PROFILES[profile_name]
        except Exception as e:
            logger.error("profile_load_error", error=str(e))
    
    profile_name = "testnet" if os.getenv("BYBIT_TESTNET", "True").lower() == "true" else "mainnet_conservative"
    logger.info("profile_default", profile=profile_name)
    return PROFILES[profile_name]

def save_profile(profile_name: str) -> bool:
    global _current_profile
    
    if profile_name not in PROFILES:
        logger.error("profile_not_found", profile=profile_name)
        return False
    
    try:
        os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
        with open(PROFILE_FILE, "w") as f:
            json.dump({"profile": profile_name}, f)
        
        _current_profile = PROFILES[profile_name]
        logger.info("profile_saved", profile=profile_name)
        return True
    except Exception as e:
        logger.error("profile_save_error", error=str(e))
        return False

def get_all_profiles() -> Dict[str, Dict[str, Any]]:
    result = {}
    for key, profile in PROFILES.items():
        result[key] = {
            "name": profile.name,
            "description": profile.description,
            "is_testnet": profile.is_testnet,
            "params": {
                "max_spread": profile.max_spread,
                "max_leverage": profile.max_leverage,
                "max_daily_loss": profile.max_daily_loss,
                "max_position_size": profile.max_position_size,
                "stop_loss_pct": profile.stop_loss_pct,
                "take_profit_pct": profile.take_profit_pct,
                "min_adx_entry": profile.min_adx_entry,
                "risk_per_trade": profile.risk_per_trade
            }
        }
    return result

def apply_profile_to_settings():
    from antigravity.config import settings
    
    profile = get_current_profile()
    
    settings.MAX_SPREAD = profile.max_spread
    settings.MAX_LEVERAGE = profile.max_leverage
    settings.MAX_DAILY_LOSS = profile.max_daily_loss
    settings.MAX_POSITION_SIZE = profile.max_position_size
    settings.MAX_SINGLE_TRADE_LOSS = profile.max_single_trade_loss
    settings.STOP_LOSS_PCT = profile.stop_loss_pct
    settings.TAKE_PROFIT_PCT = profile.take_profit_pct
    settings.TRAILING_STOP_TRIGGER = profile.trailing_stop_trigger
    settings.MIN_HOLD_TIME = profile.min_hold_time
    settings.COOLDOWN_AFTER_LOSS = profile.cooldown_after_loss
    settings.SESSION_BLACKLIST = profile.session_blacklist
    settings.MIN_ADX_ENTRY = profile.min_adx_entry
    settings.MAX_ATR_PCT = profile.max_atr_pct
    settings.BYBIT_TESTNET = profile.is_testnet
    
    logger.info("profile_applied", profile=profile.name)
    return profile
