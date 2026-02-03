import pandas as pd
import ta
import time
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
    volatility: float  # ATR
    trend_strength: float # ADX
    last_updated: float

class MarketRegimeDetector:
    """
    Detects market regime based on 4 states:
    1. Trending Up: EMA20 > EMA50, Price > both, ADX > 25, MACD Hist > 0
    2. Trending Down: EMA20 < EMA50, Price < both, ADX > 25, MACD Hist < 0
    3. Ranging: ADX < 20 or Bollinger Band Width narrowing
    4. High Volatility: ATR > 150% of avg or Volume > 200% of avg
    """
    def __init__(self, lookback_period: int = 100):
        self.lookback_period = lookback_period
        self.regimes: Dict[str, MarketRegimeData] = {}

    def analyze(self, symbol: str, klines: List[Dict]) -> MarketRegimeData:
        if len(klines) < 50:
            return MarketRegimeData(symbol, MarketRegime.UNCERTAIN, 0, 0, 0, 0)

        df = pd.DataFrame(klines)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # 1. Trend Indicators
        ema20 = ta.trend.EMAIndicator(close=df['close'], window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(close=df['close'], window=50).ema_indicator()
        adx_ind = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
        adx = adx_ind.adx().iloc[-1]
        macd_ind = ta.trend.MACD(close=df['close'])
        macd_hist = macd_ind.macd_diff().iloc[-1]

        # 2. Volatility Indicators
        atr_ind = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_ind.average_true_range()
        curr_atr = atr.iloc[-1]
        avg_atr = atr.mean()

        # 3. Bollinger Bands for Ranging
        bb = ta.volatility.BollingerBands(close=df['close'])
        bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
        curr_bbw = bb_width.iloc[-1]
        avg_bbw = bb_width.mean()

        # 4. Volume
        curr_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].mean()

        curr_price = df['close'].iloc[-1]
        curr_ema20 = ema20.iloc[-1]
        curr_ema50 = ema50.iloc[-1]

        # Classification Logic
        regime = MarketRegime.UNCERTAIN

        # Priority 1: High Volatility
        if curr_atr > 1.5 * avg_atr or curr_vol > 2.0 * avg_vol:
            regime = MarketRegime.VOLATILE

        # Priority 2: Trending Up
        elif curr_ema20 > curr_ema50 and curr_price > curr_ema20 and adx > 25 and macd_hist > 0:
            regime = MarketRegime.TRENDING_UP

        # Priority 3: Trending Down
        elif curr_ema20 < curr_ema50 and curr_price < curr_ema20 and adx > 25 and macd_hist < 0:
            regime = MarketRegime.TRENDING_DOWN

        # Priority 4: Ranging
        elif adx < 20 or curr_bbw < avg_bbw:
            regime = MarketRegime.RANGING

        else:
            regime = MarketRegime.UNCERTAIN

        data = MarketRegimeData(
            symbol=symbol,
            regime=regime,
            adx=adx,
            volatility=curr_atr,
            trend_strength=adx,
            last_updated=time.time()
        )

        self.regimes[symbol] = data

        # Persist to DB
        try:
             from antigravity.database import db
             db.save_market_regime(symbol, regime.value, adx, curr_atr)
        except Exception:
             pass

        return data

# Global Instance
market_regime_detector = MarketRegimeDetector()
