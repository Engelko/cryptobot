import aiohttp
import json
from typing import Optional, Dict, Any
from antigravity.config import settings
from antigravity.logging import get_logger

logger = get_logger("ai_client")

class AIClient:
    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL

    async def analyze_market(self, market_summary: str) -> Dict[str, Any]:
        """
        Send market summary to LLM and get sentiment analysis.
        Expected JSON response: {"score": float, "reasoning": str}
        """
        if not self.api_key:
            logger.warning("ai_client_no_key", message="LLM_API_KEY not set. Skipping analysis.")
            return {"score": 0.0, "reasoning": "AI Disabled"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
        Analyze the following crypto market data and return a JSON object with:
        - "score": A float between -1.0 (Bearish) and 1.0 (Bullish).
        - "reasoning": A brief explanation.
        
        Data:
        {market_summary}
        """
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a crypto market analyst. Respond ONLY in JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error("ai_api_error", status=response.status, response=text)
                        return {"score": 0.0, "reasoning": f"API Error {response.status}"}
                    
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Parse JSON from content (handle potential formatting issues)
                    try:
                        # Strip markdown code blocks if present
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                            
                        result = json.loads(content)
                        return result
                    except json.JSONDecodeError:
                        logger.error("ai_json_parse_error", content=content)
                        return {"score": 0.0, "reasoning": "Parse Error"}

        except Exception as e:
            logger.error("ai_request_failed", error=str(e))
            return {"score": 0.0, "reasoning": f"Request Failed: {str(e)}"}
