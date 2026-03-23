"""
AI Market Analyzer
Uses AI models (Alibaba, DeepSeek, OpenAI) to analyze market data
and provide trading insights.
"""
import json
import pandas as pd
from typing import Dict, Any, Optional
from antigravity.ai_provider import ai_provider
from antigravity.logging import get_logger
from antigravity.config import settings

logger = get_logger("ai_market_analyzer")

class AIMarketAnalyzer:
    """
    AI-powered market analysis using various LLM providers.
    Provides sentiment analysis, trend predictions, and trading recommendations.
    """
    
    SYSTEM_PROMPT = """You are an expert cryptocurrency trading analyst with deep knowledge of technical analysis, market patterns, and risk management.

Analyze the provided market data and return a JSON response with the following fields:
{
    "sentiment": float,           // -1.0 to 1.0, where -1 is very bearish, 1 is very bullish
    "confidence": float,          // 0.0 to 1.0, confidence in the analysis
    "reasoning": string,          // Detailed explanation of the analysis
    "recommendation": string,     // "BUY", "SELL", or "HOLD"
    "risk_level": string,         // "LOW", "MEDIUM", or "HIGH"
    "key_factors": [string],      // List of key factors influencing the decision
    "technical_score": float,     // 0.0 to 1.0, technical indicator score
    "market_regime": string,      // Current market regime assessment
    "time_horizon": string        // "SHORT", "MEDIUM", or "LONG" term
}

Guidelines:
- Be data-driven and objective
- Consider multiple timeframes
- Evaluate risk carefully
- Provide specific price levels if relevant
- Explain the reasoning clearly
"""
    
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize analyzer with specific provider and model.
        If not specified, uses settings from config.
        """
        self.provider = provider or settings.AI_PROVIDER
        self.model = model
        self.client = None
        self._init_client()
        logger.info("ai_analyzer_initialized", provider=self.provider, model=self.model)
    
    def _init_client(self):
        """Initialize LLM client"""
        self.client = ai_provider.get_client(self.provider, self.model)
        if self.client:
            self.model = self.client.model_id
    
    def switch_model(self, model: str) -> bool:
        """Switch to different model"""
        if ai_provider.switch_model(model):
            self.model = model
            self._init_client()
            logger.info("analyzer_model_switched", model=model)
            return True
        return False
    
    def switch_provider(self, provider: str) -> bool:
        """Switch to different provider"""
        if ai_provider.switch_provider(provider):
            self.provider = provider
            self._init_client()
            logger.info("analyzer_provider_switched", provider=provider)
            return True
        return False
    
    async def analyze_market_data(
        self, 
        symbol: str, 
        klines_df: pd.DataFrame,
        regime: str = "UNKNOWN",
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze market data and return trading signal.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            klines_df: DataFrame with OHLCV data
            regime: Current market regime
            additional_context: Additional context for analysis
        
        Returns:
            Dictionary with analysis results
        """
        if not self.client:
            logger.error("analyzer_no_client", provider=self.provider)
            return self._default_response()
        
        if klines_df.empty or len(klines_df) < 5:
            logger.warning("analyzer_insufficient_data", symbol=symbol, rows=len(klines_df))
            return self._default_response()
        
        try:
            # Prepare market summary
            market_data = self._prepare_market_summary(symbol, klines_df, regime)
            
            # Add additional context if provided
            if additional_context:
                market_data += f"\n\nAdditional Context:\n{additional_context}"
            
            # Create messages
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this market data:\n{market_data}"}
            ]
            
            # Get model-specific config
            model_config = ai_provider.MODEL_CONFIGS.get(self.model, {})
            
            # Call AI
            logger.info("analyzer_request", symbol=symbol, provider=self.provider, model=self.model)
            response = await self.client.chat(
                messages, 
                temperature=model_config.get("temperature", 0.3),
                max_tokens=model_config.get("max_tokens", 4096)
            )
            
            # Parse JSON response
            result = self._parse_response(response)
            result["symbol"] = symbol
            result["provider"] = self.provider
            result["model"] = self.model
            
            logger.info(
                "analyzer_complete", 
                symbol=symbol,
                sentiment=result.get("sentiment"),
                recommendation=result.get("recommendation"),
                confidence=result.get("confidence")
            )
            
            return result
            
        except Exception as e:
            logger.error("analyzer_failed", symbol=symbol, error=str(e))
            return self._default_response()
    
    def _prepare_market_summary(
        self, 
        symbol: str, 
        df: pd.DataFrame, 
        regime: str
    ) -> str:
        """Prepare market data summary for AI analysis"""
        
        # Get latest and previous data
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Calculate changes
        price_change = ((latest['close'] - prev['close']) / prev['close'] * 100) if prev['close'] != 0 else 0
        volume_change = ((latest['volume'] - prev['volume']) / prev['volume'] * 100) if prev['volume'] != 0 else 0
        
        # Calculate price range
        price_high = df['high'].max()
        price_low = df['low'].min()
        price_range = ((price_high - price_low) / price_low * 100) if price_low != 0 else 0
        
        # Get indicators if available
        indicators = {}
        indicator_fields = ['rsi', 'macd', 'adx', 'atr', 'bb_h', 'bb_l', 'sma_20', 'ema_20']
        for field in indicator_fields:
            if field in latest:
                indicators[field] = latest[field]
        
        # Build summary
        summary = f"""
Symbol: {symbol}
Current Market Regime: {regime}

Price Data (Current Candle):
- Open: {latest.get('open', 'N/A')}
- High: {latest.get('high', 'N/A')}
- Low: {latest.get('low', 'N/A')}
- Close: {latest.get('close', 'N/A')}
- Volume: {latest.get('volume', 'N/A')}

Price Changes:
- Current Change: {price_change:.2f}%
- Volume Change: {volume_change:.2f}%
- Session Range: {price_range:.2f}%
- Session High: {price_high}
- Session Low: {price_low}
"""
        
        # Add indicators if available
        if indicators:
            summary += "\nTechnical Indicators:\n"
            for name, value in indicators.items():
                if pd.notna(value):
                    summary += f"- {name.upper()}: {value:.4f}\n"
        
        # Add recent candles summary
        summary += f"\nRecent Price Action (Last {min(5, len(df))} candles):\n"
        recent = df.tail(min(5, len(df)))
        for idx, row in recent.iterrows():
            summary += f"- O:{row.get('open', 'N/A'):.2f} H:{row.get('high', 'N/A'):.2f} L:{row.get('low', 'N/A'):.2f} C:{row.get('close', 'N/A'):.2f} V:{row.get('volume', 'N/A'):.2f}\n"
        
        return summary
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from AI"""
        try:
            # Try to find JSON in the response
            response = response.strip()
            
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response)
            
            # Validate required fields
            required_fields = ["sentiment", "confidence", "reasoning", "recommendation"]
            for field in required_fields:
                if field not in result:
                    logger.warning("analyzer_missing_field", field=field)
                    result[field] = self._default_response()[field]
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error("analyzer_invalid_json", response=response[:200], error=str(e))
            return self._default_response()
        except Exception as e:
            logger.error("analyzer_parse_error", error=str(e))
            return self._default_response()
    
    def _default_response(self) -> Dict[str, Any]:
        """Return default neutral response"""
        return {
            "sentiment": 0.0,
            "confidence": 0.5,
            "reasoning": "Analysis unavailable - using default neutral stance",
            "recommendation": "HOLD",
            "risk_level": "MEDIUM",
            "key_factors": ["Insufficient data or analysis error"],
            "technical_score": 0.5,
            "market_regime": "UNKNOWN",
            "time_horizon": "MEDIUM",
            "symbol": "",
            "provider": self.provider,
            "model": self.model
        }
    
    def get_available_models(self) -> list:
        """Get list of available models"""
        return ai_provider.list_available_models(self.provider)
    
    def get_model_info(self, model: Optional[str] = None) -> Dict:
        """Get information about model"""
        model = model or self.model
        return ai_provider.get_model_info(model)

# Global instance
market_analyzer = AIMarketAnalyzer()
