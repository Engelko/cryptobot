import pandas as pd
import numpy as np
import ta
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from antigravity.strategy import BaseStrategy, Signal, SignalType, TakeProfitLevel
from antigravity.event import MarketDataEvent, KlineEvent, OrderUpdateEvent
from antigravity.strategies.config import DynamicRiskLeverageConfig
from antigravity.logging import get_logger
from antigravity.performance_tracker import PerformanceTracker, Trade, TradeResult
from antigravity.config import settings
from datetime import datetime, timezone
import uuid

logger = get_logger("strategy_dynamic_risk")

class EntryType(Enum):
    TYPE_A = "A"  # Ideal entry - high confidence
    TYPE_B = "B"  # Good entry - medium confidence  
    TYPE_C = "C"  # Weak entry - low confidence

class TrendDirection(Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"

@dataclass
class MarketAnalysis:
    trend_direction: TrendDirection
    trend_strength: float  # 0-1
    key_levels: Dict[str, float]  # support, resistance
    volume_analysis: Dict[str, Any]
    technical_signals: Dict[str, Any]
    entry_type: EntryType
    leverage_recommendation: float
    risk_percentage: float

class DynamicRiskLeverageStrategy(BaseStrategy):
    def __init__(self, config: DynamicRiskLeverageConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        
        # Data storage
        self.klines_main = {s: [] for s in symbols}
        self.klines_macro = {s: [] for s in symbols}
        self.last_analysis_time = {s: 0 for s in symbols}
        self.analysis_cache: Dict[str, Optional[MarketAnalysis]] = {s: None for s in symbols}
        self.last_signal_time = {s: 0 for s in symbols}  # Cooldown for signals
        self.performance_tracker = PerformanceTracker()
        
        # Minimum data requirements
        self.min_main_klines = 100  # Minimum candles for 1h timeframe
        self.min_macro_klines = 50   # Minimum candles for 4h timeframe

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None

            # Store klines for both timeframes
            self._store_kline(event)
            
            # Telemetry
            self.ticks_processed += 1
            if self.ticks_processed % 10 == 0:
                self._log_heartbeat(event.symbol)
            
            # Signal cooldown: prevent duplicate signals within 60 seconds
            current_time = event.timestamp
            if current_time - self.last_signal_time[event.symbol] < 60000:  # 60 seconds in milliseconds
                return None
            
            # Check if we have enough data
            if not self._has_enough_data(event.symbol):
                return None
            
            # Perform market analysis
            analysis = await self._analyze_market(event.symbol)
            if analysis is None:
                return None
            
            # Generate signal based on analysis
            signal = self._generate_signal(event.symbol, analysis)
            if signal:
                # Update signal cooldown timestamp
                self.last_signal_time[event.symbol] = int(current_time)
                    
            return signal
            
        return None

    def _store_kline(self, event: KlineEvent):
        """Store kline data for both timeframes"""
        # Main timeframe
        self.klines_main[event.symbol].append({
            "timestamp": event.timestamp,
            "open": event.open,
            "high": event.high,
            "low": event.low,
            "close": event.close,
            "volume": event.volume
        })
        
        # Maintain maximum size
        max_size = max(self.min_main_klines, self.min_macro_klines) + 200
        if len(self.klines_main[event.symbol]) > max_size:
            self.klines_main[event.symbol].pop(0)

    def _has_enough_data(self, symbol: str) -> bool:
        """Check if we have sufficient data for analysis"""
        return (len(self.klines_main[symbol]) >= self.min_main_klines)

    def _log_heartbeat(self, symbol: str):
        """Log strategy heartbeat"""
        main_count = len(self.klines_main[symbol])
        status = f"Data: {main_count}/{self.min_main_klines}"
        if main_count < self.min_main_klines:
            status = f"Collecting {main_count}/{self.min_main_klines}"
        else:
            analysis = self.analysis_cache.get(symbol)
            if analysis:
                status = f"Trend: {analysis.trend_direction.value} | Entry: {analysis.entry_type.value}"
        
        logger.info("strategy_heartbeat", name=self.name, symbol=symbol, status=status)

    async def _analyze_market(self, symbol: str) -> Optional[MarketAnalysis]:
        """Comprehensive market analysis"""
        current_time = self.klines_main[symbol][-1]["timestamp"]
        
        # Cache analysis for performance
        if (self.analysis_cache[symbol] and 
            current_time - self.last_analysis_time[symbol] < 300):  # 5 minutes cache
            return self.analysis_cache[symbol]
        
        try:
            # Prepare data
            df_main = self._prepare_dataframe(symbol, self.klines_main[symbol])
            
            # Analyze each component
            trend_analysis = self._analyze_trend(df_main)
            levels_analysis = self._analyze_support_resistance(df_main)
            volume_analysis = self._analyze_volume(df_main)
            technical_analysis = self._analyze_technical_indicators(df_main)
            
            # Determine entry type and risk parameters
            entry_analysis = self._determine_entry_type(
                trend_analysis, levels_analysis, volume_analysis, technical_analysis
            )
            
            # Check filters
            if not self._pass_quality_filters(
                trend_analysis, volume_analysis, technical_analysis, symbol
            ):
                self.last_analysis_time[symbol] = current_time
                self.analysis_cache[symbol] = None
                return None
            
            # Create comprehensive analysis
            analysis = MarketAnalysis(
                trend_direction=trend_analysis["direction"],
                trend_strength=trend_analysis["strength"],
                key_levels=levels_analysis,
                volume_analysis=volume_analysis,
                technical_signals=technical_analysis,
                entry_type=entry_analysis["type"],
                leverage_recommendation=entry_analysis["leverage"],
                risk_percentage=entry_analysis["risk"]
            )
            
            # Cache result
            self.analysis_cache[symbol] = analysis
            self.last_analysis_time[symbol] = current_time
            
            return analysis
            
        except Exception as e:
            logger.error("market_analysis_failed", symbol=symbol, error=str(e))
            return None

    def _prepare_dataframe(self, symbol: str, klines: List[Dict]) -> pd.DataFrame:
        """Convert klines to DataFrame with indicators"""
        df = pd.DataFrame(klines)
        
        # Calculate technical indicators
        df["ema_fast"] = df["close"].ewm(span=self.config.ema_fast).mean()
        df["ema_slow"] = df["close"].ewm(span=self.config.ema_slow).mean()
        
        # RSI calculation
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.config.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.config.rsi_period).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # MACD calculation
        exp1 = df["close"].ewm(span=self.config.macd_fast).mean()
        exp2 = df["close"].ewm(span=self.config.macd_slow).mean()
        df["macd"] = exp1 - exp2
        df["macd_signal"] = df["macd"].ewm(span=self.config.macd_signal).mean()
        
        df["volume_ma"] = df["volume"].rolling(window=self.config.volume_ma_period).mean()
        
        # ATR for volatility
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["atr"] = true_range.rolling(window=14).mean()
        
        return df

    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze trend direction and strength"""
        latest = df.iloc[-1]
        
        # Trend direction based on EMAs
        if latest["ema_fast"] > latest["ema_slow"]:
            if latest["close"] > latest["ema_fast"]:
                direction = TrendDirection.UPTREND
            else:
                direction = TrendDirection.SIDEWAYS
        else:
            if latest["close"] < latest["ema_fast"]:
                direction = TrendDirection.DOWNTREND
            else:
                direction = TrendDirection.SIDEWAYS
        
        # Trend strength based on EMA separation and price position
        ema_separation = abs(latest["ema_fast"] - latest["ema_slow"]) / latest["close"]
        price_position = abs(latest["close"] - latest["ema_slow"]) / latest["close"]
        
        # Combine into strength score (0-1)
        strength = min(1.0, (ema_separation + price_position) * 10)
        
        return {
            "direction": direction,
            "strength": strength,
            "ema_fast": latest["ema_fast"],
            "ema_slow": latest["ema_slow"],
            "price_vs_emas": {
                "above_fast": latest["close"] > latest["ema_fast"],
                "above_slow": latest["close"] > latest["ema_slow"]
            }
        }

    def _analyze_support_resistance(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, float]:
        """Identify key support and resistance levels"""
        if lookback is None:
            lookback = self.config.support_resistance_lookback
        
        recent_df = df.tail(lookback)
        current_price = df.iloc[-1]["close"]
        
        # Find swing highs and lows
        highs = recent_df["high"].values
        lows = recent_df["low"].values
        
        # Simple approach: use recent high/low zones
        resistance_levels = []
        support_levels = []
        
        for i in range(2, len(highs) - 2):
            # Local maxima for resistance
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and 
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                resistance_levels.append(highs[i])
            
            # Local minima for support
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and 
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                support_levels.append(lows[i])
        
        # Get closest levels
        resistance = min(resistance_levels, key=lambda x: abs(x - current_price)) if resistance_levels else current_price * 1.05
        support = max(support_levels, key=lambda x: abs(x - current_price)) if support_levels else current_price * 0.95
        
        return {
            "support": support,
            "resistance": resistance,
            "distance_to_support": (current_price - support) / current_price,
            "distance_to_resistance": (resistance - current_price) / current_price
        }

    def _analyze_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume patterns"""
        latest = df.iloc[-1]
        current_volume = latest["volume"]
        avg_volume = latest["volume_ma"]
        
        # Volume comparison
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Volume trend
        recent_volumes = df["volume"].tail(10)
        volume_trend = "increasing" if recent_volumes.is_monotonic_increasing else "decreasing" if recent_volumes.is_monotonic_decreasing else "neutral"
        
        return {
            "current": current_volume,
            "average": avg_volume,
            "ratio": volume_ratio,
            "trend": volume_trend,
            "is_above_average": volume_ratio > self.config.min_volume_multiplier,
            "is_low_volume": volume_ratio < self.config.max_volume_drop_threshold
        }

    def _analyze_technical_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze technical indicators for signals"""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # RSI analysis
        rsi = latest["rsi"]
        rsi_zone = "neutral"
        if rsi < self.config.rsi_extreme_oversold:
            rsi_zone = "extreme_oversold"
        elif rsi < self.config.rsi_oversold:
            rsi_zone = "oversold"
        elif rsi > self.config.rsi_extreme_overbought:
            rsi_zone = "extreme_overbought"
        elif rsi > self.config.rsi_overbought:
            rsi_zone = "overbought"
        
        # MACD analysis
        macd_cross = None
        if prev["macd"] <= prev["macd_signal"] and latest["macd"] > latest["macd_signal"]:
            macd_cross = "bullish"
        elif prev["macd"] >= prev["macd_signal"] and latest["macd"] < latest["macd_signal"]:
            macd_cross = "bearish"
        
        return {
            "rsi": {
                "value": rsi,
                "zone": rsi_zone,
                "is_neutral": self.config.rsi_oversold <= rsi <= self.config.rsi_overbought
            },
            "macd": {
                "diff": latest["macd"],
                "signal": latest["macd_signal"],
                "cross": macd_cross,
                "is_bullish": latest["macd"] > latest["macd_signal"]
            },
            "price": latest["close"],
            "atr": latest["atr"]
        }

    def _determine_entry_type(self, trend: Dict, levels: Dict, volume: Dict, technical: Dict) -> Dict[str, Any]:
        """Determine entry type and corresponding risk parameters"""
        score = 0
        reasons = []
        
        # Trend scoring
        if trend["direction"] == TrendDirection.UPTREND:
            score += 3
            reasons.append("strong_uptrend")
        elif trend["direction"] == TrendDirection.DOWNTREND:
            score -= 3
            reasons.append("strong_downtrend")
        else:
            reasons.append("sideways_market")
        
        # Level proximity scoring
        dist_to_support = abs(levels["distance_to_support"])
        if 0.015 <= dist_to_support <= 0.03:  # 1.5%-3% from support
            score += 2
            reasons.append("good_support_distance")
        elif dist_to_support < 0.015:  # Too close to support
            score -= 1
            reasons.append("too_close_to_support")
        
        # Volume scoring
        if volume["is_above_average"]:
            score += 2
            reasons.append("high_volume_confirmation")
        elif volume["is_low_volume"]:
            score -= 2
            reasons.append("low_volume_warning")
        
        # RSI scoring
        if technical["rsi"]["is_neutral"]:
            score += 1
            reasons.append("neutral_rsi")
        elif technical["rsi"]["zone"] in ["extreme_oversold", "extreme_overbought"]:
            score -= 2
            reasons.append("extreme_rsi_zone")
        
        # MACD scoring
        if technical["macd"]["cross"] == "bullish":
            score += 2
            reasons.append("bullish_macd_cross")
        elif technical["macd"]["cross"] == "bearish":
            score -= 2
            reasons.append("bearish_macd_cross")
        
        # Determine entry type based on score
        if score >= 6:
            entry_type = EntryType.TYPE_A
            leverage = self.config.high_risk_leverage  # CONSERVATIVE: 2.5x
            risk = self.config.type_a_risk
        elif score >= 2:
            entry_type = EntryType.TYPE_B
            leverage = self.config.medium_risk_leverage  # MODERATE: 6.0x
            risk = self.config.type_b_risk
        elif score >= -1:
            entry_type = EntryType.TYPE_C
            leverage = self.config.low_risk_leverage  # AGGRESSIVE: 9.0x
            risk = self.config.type_c_risk
        else:
            entry_type = EntryType.TYPE_C  # Very weak signal
            leverage = self.config.low_risk_leverage * 0.8  # Even lower leverage
            risk = self.config.type_c_risk * 0.8
        
        return {
            "type": entry_type,
            "score": score,
            "leverage": leverage,
            "risk": risk,
            "reasons": reasons
        }

    def _pass_quality_filters(self, trend: Dict, volume: Dict, technical: Dict, symbol: str) -> bool:
        """Apply quality filters to avoid bad trades"""
        
        # Filter 1: No trading in sideways markets
        if trend["direction"] == TrendDirection.SIDEWAYS:
            logger.info("filter_sideways_market", symbol=symbol)
            return False
        
        # Filter 2: Avoid extreme RSI zones
        if technical["rsi"]["zone"] in ["extreme_oversold", "extreme_overbought"]:
            logger.info("filter_extreme_rsi", symbol=symbol, zone=technical["rsi"]["zone"])
            return False
        
        # Filter 3: Volume must be adequate
        if volume["is_low_volume"]:
            logger.info("filter_low_volume", symbol=symbol, ratio=volume["ratio"])
            return False
        
        # Filter 4: Daily loss limit
        if self.performance_tracker.check_daily_loss_limit(self.config.daily_loss_limit):
            logger.info("filter_daily_loss_limit", symbol=symbol)
            return False
        
        # Filter 5: Consecutive losses
        if self.performance_tracker.consecutive_losses >= 3:
            logger.info("filter_consecutive_losses", symbol=symbol, count=self.performance_tracker.consecutive_losses)
            return False
        
        return True

    def _generate_signal(self, symbol: str, analysis: MarketAnalysis) -> Optional[Signal]:
        """Generate trading signal based on analysis"""
        current_price = analysis.technical_signals["price"]
        
        # Determine signal direction based on trend
        if analysis.trend_direction == TrendDirection.UPTREND:
            signal_type = SignalType.BUY
            
            # Additional confirmation needed for uptrend entries
            if (not analysis.technical_signals["rsi"]["is_neutral"] or
                not analysis.volume_analysis["is_above_average"]):
                return None
                
        elif analysis.trend_direction == TrendDirection.DOWNTREND:
            signal_type = SignalType.SELL
            
            # Additional confirmation needed for downtrend entries  
            if (not analysis.technical_signals["rsi"]["is_neutral"] or
                not analysis.volume_analysis["is_above_average"]):
                return None
        else:
            return None  # No signal in sideways market
        
        # Calculate position size based on risk and leverage
        risk_percentage = analysis.risk_percentage
        atr = analysis.technical_signals["atr"]
        stop_distance = atr * 1.5  # 1.5x ATR for stop loss
        
        # Ensure stop distance is reasonable (1-2% max)
        stop_distance_pct = min(stop_distance / current_price, 0.02)
        
        # Calculate stop loss price
        if signal_type == SignalType.BUY:
            stop_loss_price = current_price * (1 - stop_distance_pct)
        else:
            stop_loss_price = current_price * (1 + stop_distance_pct)
        
        # Calculate quantity
        # Use MAX_POSITION_SIZE as the capital basis for risk calculation to ensure safety
        risk_capital = settings.MAX_POSITION_SIZE * risk_percentage
        stop_loss_value_per_unit = current_price * stop_distance_pct

        # Calculate raw quantity based on risk
        raw_quantity = risk_capital / stop_loss_value_per_unit if stop_loss_value_per_unit > 0 else 0

        # Cap at MAX_POSITION_SIZE
        max_qty_allowed = settings.MAX_POSITION_SIZE / current_price
        quantity = min(raw_quantity, max_qty_allowed)
        
        # Calculate take profit levels based on entry type
        tp_levels = self._calculate_take_profit_levels(
            current_price, stop_loss_price, signal_type, analysis.entry_type, atr
        )
        
        # Add detailed reason
        reasons_str = ", ".join([
            f"Entry: {analysis.entry_type.value}",
            f"Trend: {analysis.trend_direction.value}",
            f"Leverage: {analysis.leverage_recommendation:.1f}x",
            f"Risk: {analysis.risk_percentage:.1%}",
            f"R:R = 1:{self._calculate_risk_reward_ratio(current_price, stop_loss_price, tp_levels):.1f}"
        ])
        
        return Signal(
            type=signal_type,
            symbol=symbol,
            price=current_price,
            quantity=quantity,
            reason=f"DynamicRiskLeverage - {reasons_str}",
            stop_loss=stop_loss_price,
            take_profit_levels=tp_levels,
            leverage=analysis.leverage_recommendation,
            risk_percentage=analysis.risk_percentage,
            trailing_stop=analysis.entry_type == EntryType.TYPE_A  # Trail on best entries
        )

    def _calculate_take_profit_levels(self, entry_price: float, stop_loss: float, 
                                   signal_type: SignalType, entry_type: EntryType, 
                                   atr: float) -> List[TakeProfitLevel]:
        """Calculate partial take profit levels"""
        risk = abs(entry_price - stop_loss)
        
        tp_levels = []
        
        if signal_type == SignalType.BUY:
            # Type A entry: Aggressive profit taking
            if entry_type == EntryType.TYPE_A:
                tp1_price = entry_price + (risk * 1.5)  # 1.5x risk
                tp2_price = entry_price + (risk * 3.0)  # 3x risk
                tp3_price = entry_price + (risk * 5.0)  # 5x risk
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 0.5, "Quick profit - Type A entry"),
                    TakeProfitLevel(tp2_price, 0.3, "Medium target - Type A entry"),
                    TakeProfitLevel(tp3_price, 0.2, "Full target - Type A entry")
                ]
            
            # Type B entry: Standard profit taking
            elif entry_type == EntryType.TYPE_B:
                tp1_price = entry_price + (risk * 2.0)  # 2x risk
                tp2_price = entry_price + (risk * 4.0)  # 4x risk
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 0.6, "First target - Type B entry"),
                    TakeProfitLevel(tp2_price, 0.4, "Full target - Type B entry")
                ]
            
            # Type C entry: Conservative profit taking
            else:
                tp1_price = entry_price + (risk * 1.5)  # 1.5x risk
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 1.0, "Single target - Type C entry")
                ]
        
        else:  # SELL signal
            # Type A entry: Aggressive profit taking
            if entry_type == EntryType.TYPE_A:
                tp1_price = entry_price - (risk * 1.5)
                tp2_price = entry_price - (risk * 3.0)
                tp3_price = entry_price - (risk * 5.0)
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 0.5, "Quick profit - Type A entry"),
                    TakeProfitLevel(tp2_price, 0.3, "Medium target - Type A entry"),
                    TakeProfitLevel(tp3_price, 0.2, "Full target - Type A entry")
                ]
            
            # Type B entry: Standard profit taking
            elif entry_type == EntryType.TYPE_B:
                tp1_price = entry_price - (risk * 2.0)
                tp2_price = entry_price - (risk * 4.0)
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 0.6, "First target - Type B entry"),
                    TakeProfitLevel(tp2_price, 0.4, "Full target - Type B entry")
                ]
            
            # Type C entry: Conservative profit taking
            else:
                tp1_price = entry_price - (risk * 1.5)
                
                tp_levels = [
                    TakeProfitLevel(tp1_price, 1.0, "Single target - Type C entry")
                ]
        
        return tp_levels

    def _calculate_risk_reward_ratio(self, entry_price: float, stop_loss: float, 
                                   tp_levels: List[TakeProfitLevel]) -> float:
        """Calculate average risk:reward ratio"""
        if not tp_levels:
            return 1.0
        
        risk = abs(entry_price - stop_loss)
        total_reward = 0
        total_weight = 0
        
        for tp in tp_levels:
            reward = abs(tp.price - entry_price)
            weight = tp.quantity_percentage
            total_reward += reward * weight
            total_weight += weight
        
        avg_reward = total_reward / total_weight if total_weight > 0 else 0
        return avg_reward / risk if risk > 0 else 1.0

    async def on_order_update(self, event):
        """Handle order updates and track performance"""
        # Simplified implementation - would need to track order states properly
        logger.info("order_update_received", symbol=getattr(event, 'symbol', 'unknown'))