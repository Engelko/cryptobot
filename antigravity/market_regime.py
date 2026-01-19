import pandas as pd
import ta
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
from antigravity.logging import get_logger

logger = get_logger("market_regime")

class MarketRegime(Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNCERTAIN = "UNCERTAIN"

@dataclass
class MarketRegimeData:
    symbol: str
    regime: MarketRegime
    adx: float
    volatility: float  # ATR normalized or similar
    trend_strength: float # 0-100
    last_updated: float

class MarketRegimeDetector:
    """
    Detects market regime based on recent price history (klines).
    Uses ADX for trend strength, Bollinger Band Width / ATR for volatility.
    """
    def __init__(self, lookback_period: int = 50):
        self.lookback_period = lookback_period
        self.regimes: Dict[str, MarketRegimeData] = {}

    def analyze(self, symbol: str, klines: List[Dict]) -> MarketRegimeData:
        """
        Analyze klines to determine regime.
        Klines expected to be list of dicts with keys: 'open', 'high', 'low', 'close', 'volume'
        """
        if len(klines) < self.lookback_period:
            return MarketRegimeData(symbol, MarketRegime.UNCERTAIN, 0, 0, 0, 0)

        df = pd.DataFrame(klines)
        # Convert columns to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # 1. Calculate ADX (Trend Strength)
        adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
        adx = adx_indicator.adx().iloc[-1]

        # 2. Calculate EMAs for Direction
        ema_short = ta.trend.EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        ema_long = ta.trend.EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]

        # 3. Calculate Volatility (ATR %)
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_indicator.average_true_range().iloc[-1]
        close_price = df['close'].iloc[-1]
        volatility_pct = (atr / close_price) * 100

        # 4. Determine Regime
        regime = MarketRegime.UNCERTAIN

        # ADX Thresholds
        # < 20: Weak trend / Ranging
        # > 25: Strong trend
        # > 40: Very strong trend

        if adx > 25:
            if ema_short > ema_long:
                regime = MarketRegime.TRENDING_UP
            else:
                regime = MarketRegime.TRENDING_DOWN
        elif adx < 20:
             regime = MarketRegime.RANGING

        # Volatility Override
        # If volatility is extreme (e.g. > 2-3% ATR on lower TFs, or relative spike), mark as VOLATILE
        # Simple heuristic: if recent ATR is 2x average ATR of last 50 periods
        avg_atr = atr_indicator.average_true_range().mean()
        if atr > 2.0 * avg_atr:
             regime = MarketRegime.VOLATILE

        data = MarketRegimeData(
            symbol=symbol,
            regime=regime,
            adx=adx,
            volatility=volatility_pct,
            trend_strength=adx, # Simple mapping
            last_updated=0 # Timestamp logic can be added
        )

        self.regimes[symbol] = data
        return data

# Global Instance
market_regime_detector = MarketRegimeDetector()
