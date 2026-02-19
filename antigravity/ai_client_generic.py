import aiohttp
import json
from typing import List, Dict, Any, Optional
from antigravity.logging import get_logger

logger = get_logger("ai_client_generic")

class LLMClient:
    def __init__(self, provider: str, api_key: str, model_id: str, base_url: str, **kwargs):
        self.provider = provider
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url.rstrip('/')
        self.timeout = kwargs.get("timeout", 60)
        self.max_tokens = kwargs.get("max_tokens", 1024)
        self.temperature = kwargs.get("temperature", 0.2)
        self.extra_kwargs = kwargs

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}, ...]
        Returns the assistant 'content' as string.
        """
        if not self.api_key:
            logger.error("ai_client_no_key", provider=self.provider)
            return ""

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature)
        }

        for key, val in self.extra_kwargs.items():
            if key not in ["timeout"]:
                payload[key] = val

        for key, val in kwargs.items():
            if key not in ["max_tokens", "temperature"]:
                payload[key] = val

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error("ai_api_error", status=response.status, provider=self.provider, response=text)
                        return ""

                    data = await response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        return content
                    else:
                        logger.error("ai_api_invalid_response", data=data)
                        return ""
        except Exception as e:
            logger.error("ai_request_failed", provider=self.provider, error=str(e))
            return ""
