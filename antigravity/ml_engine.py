import pandas as pd
from typing import Dict, Any, Optional, List
from antigravity.config import settings
from antigravity.logging import get_logger
from antigravity.ai_agent import ai_agent

logger = get_logger("ml_engine")

class MLEngine:
    def __init__(self):
        self.enabled = settings.ENABLE_ML
        self.agent = ai_agent
        if self.enabled:
            logger.info("ml_engine_initialized", mode="LightGBM")

    async def predict_price_movement(self, symbol: str, klines: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        Predicts price movement for a symbol based on kline history.
        """
        if not self.enabled:
            return None

        df = pd.DataFrame(klines)
        prediction = self.agent.predict(df)
        
        return prediction

# Global ML Engine
ml_engine = MLEngine()
