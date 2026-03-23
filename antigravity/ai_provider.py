"""
AI Provider Manager
Handles multiple AI providers: DeepSeek, Alibaba Model Studio, OpenAI
"""
from typing import Optional, List, Dict
from antigravity.config import settings
from antigravity.ai_client_generic import LLMClient
from antigravity.logging import get_logger

logger = get_logger("ai_provider")

class AIProviderManager:
    """
    Manage multiple AI providers with automatic fallback and model selection.
    Supports: DeepSeek, Alibaba Model Studio, OpenAI
    """
    
    PROVIDER_CONFIGS = {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat",
            "api_key_env": "LLM_API_KEY"
        },
        "alibaba": {
            "base_url": "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1",
            "default_model": "qwen3.5-plus",
            "api_key_env": "ALIBABA_API_KEY"
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4",
            "api_key_env": "LLM_API_KEY"
        }
    }
    
    # Model-specific configurations
    MODEL_CONFIGS = {
        "qwen3.5-plus": {"max_tokens": 4096, "temperature": 0.3, "thinking": True},
        "qwen3-coder-plus": {"max_tokens": 4096, "temperature": 0.2, "thinking": True},
        "qwen3-coder-next": {"max_tokens": 4096, "temperature": 0.2, "thinking": True},
        "qwen3-max-2026-01-23": {"max_tokens": 4096, "temperature": 0.3, "thinking": False},
        "kimi-k2.5": {"max_tokens": 4096, "temperature": 0.3, "thinking": True},
        "MiniMax-M2.5": {"max_tokens": 4096, "temperature": 0.3, "thinking": True},
        "glm-5": {"max_tokens": 4096, "temperature": 0.3, "thinking": True},
        "glm-4.7": {"max_tokens": 4096, "temperature": 0.3, "thinking": True},
        "deepseek-chat": {"max_tokens": 4096, "temperature": 0.3, "thinking": False},
        "gpt-4": {"max_tokens": 4096, "temperature": 0.3, "thinking": False},
        "gpt-3.5-turbo": {"max_tokens": 4096, "temperature": 0.3, "thinking": False}
    }
    
    def __init__(self):
        self._clients: Dict[str, LLMClient] = {}
        self._current_provider = settings.AI_PROVIDER
        self._current_model = self._get_default_model()
        logger.info("ai_provider_initialized", provider=self._current_provider, model=self._current_model)
    
    def _get_default_model(self) -> str:
        """Get default model for current provider"""
        if self._current_provider == "alibaba":
            return settings.ALIBABA_MODEL
        return self.PROVIDER_CONFIGS[self._current_provider]["default_model"]
    
    def _get_api_key(self, provider: str) -> str:
        """Get API key for provider"""
        if provider == "alibaba":
            return settings.ALIBABA_API_KEY
        elif provider == "deepseek":
            return settings.LLM_API_KEY
        elif provider == "openai":
            return settings.LLM_API_KEY
        return ""
    
    def get_client(self, provider: Optional[str] = None, model: Optional[str] = None) -> Optional[LLMClient]:
        """
        Get LLM client for specified provider and model.
        Creates new client if not cached.
        """
        provider = provider or self._current_provider
        config = self.PROVIDER_CONFIGS.get(provider)
        
        if not config:
            logger.error("unknown_provider", provider=provider)
            return None
        
        api_key = self._get_api_key(provider)
        if not api_key:
            logger.error("api_key_missing", provider=provider)
            return None
        
        # Use specified model or default
        if model:
            model_id = model
        elif provider == "alibaba":
            model_id = settings.ALIBABA_MODEL
        else:
            model_id = config["default_model"]
        
        # Check cache
        cache_key = f"{provider}:{model_id}"
        if cache_key in self._clients:
            return self._clients[cache_key]
        
        # Get base URL
        if provider == "alibaba":
            base_url = settings.ALIBABA_BASE_URL
        else:
            base_url = config["base_url"]
        
        # Get model-specific config
        model_config = self.MODEL_CONFIGS.get(model_id, {})
        
        # Create new client
        try:
            client = LLMClient(
                provider=provider,
                api_key=api_key,
                model_id=model_id,
                base_url=base_url,
                timeout=60,
                max_tokens=model_config.get("max_tokens", 4096),
                temperature=model_config.get("temperature", 0.3)
            )
            self._clients[cache_key] = client
            logger.info("client_created", provider=provider, model=model_id)
            return client
        except Exception as e:
            logger.error("client_creation_failed", provider=provider, error=str(e))
            return None
    
    def switch_provider(self, provider: str) -> bool:
        """Switch to different provider"""
        if provider not in self.PROVIDER_CONFIGS:
            logger.error("invalid_provider", provider=provider)
            return False
        
        self._current_provider = provider
        self._current_model = self._get_default_model()
        logger.info("provider_switched", provider=provider, model=self._current_model)
        return True
    
    def switch_model(self, model: str) -> bool:
        """Switch to different model (for current provider)"""
        if self._current_provider == "alibaba":
            if model not in settings.ALIBABA_AVAILABLE_MODELS:
                logger.error("invalid_model", model=model, provider=self._current_provider)
                return False
        
        self._current_model = model
        logger.info("model_switched", model=model, provider=self._current_provider)
        return True
    
    def list_available_models(self, provider: Optional[str] = None) -> List[str]:
        """List available models for provider"""
        provider = provider or self._current_provider
        
        if provider == "alibaba":
            return list(settings.ALIBABA_AVAILABLE_MODELS)
        elif provider == "openai":
            return ["gpt-4", "gpt-3.5-turbo"]
        elif provider == "deepseek":
            return ["deepseek-chat", "deepseek-coder"]
        return []
    
    def list_providers(self) -> List[str]:
        """List available providers"""
        return list(self.PROVIDER_CONFIGS.keys())
    
    def get_current_config(self) -> Dict:
        """Get current provider and model configuration"""
        return {
            "provider": self._current_provider,
            "model": self._current_model,
            "available_models": self.list_available_models(),
            "providers": self.list_providers()
        }
    
    def get_model_info(self, model: str) -> Dict:
        """Get information about specific model"""
        model_configs = {
            "qwen3.5-plus": {
                "name": "Qwen3.5 Plus",
                "context": "1M tokens",
                "strengths": ["General purpose", "Multilingual", "Long context"],
                "best_for": "General market analysis, summaries"
            },
            "qwen3-coder-plus": {
                "name": "Qwen3.5 Coder Plus",
                "context": "1M tokens",
                "strengths": ["Code analysis", "Logic", "Technical"],
                "best_for": "Strategy code analysis, technical logic"
            },
            "qwen3-coder-next": {
                "name": "Qwen3 Coder Next",
                "context": "1M tokens",
                "strengths": ["Latest coding", "Reasoning"],
                "best_for": "Complex strategy logic"
            },
            "qwen3-max-2026-01-23": {
                "name": "Qwen3 Max",
                "context": "262K tokens",
                "strengths": ["High accuracy", "Fast"],
                "best_for": "Real-time trading decisions"
            },
            "kimi-k2.5": {
                "name": "Kimi K2.5",
                "context": "262K tokens",
                "strengths": ["Long context", "Reasoning", "Analysis"],
                "best_for": "Multi-day trend analysis"
            },
            "MiniMax-M2.5": {
                "name": "MiniMax M2.5",
                "context": "196K tokens",
                "strengths": ["Fast", "Efficient"],
                "best_for": "Quick decisions, high frequency"
            },
            "glm-5": {
                "name": "GLM-5",
                "context": "202K tokens",
                "strengths": ["Balanced", "Reliable"],
                "best_for": "Balanced analysis"
            },
            "glm-4.7": {
                "name": "GLM-4.7",
                "context": "202K tokens",
                "strengths": ["Cost-effective", "Good quality"],
                "best_for": "Cost-conscious trading"
            },
            "deepseek-chat": {
                "name": "DeepSeek Chat",
                "context": "64K tokens",
                "strengths": ["General purpose"],
                "best_for": "General analysis"
            },
            "gpt-4": {
                "name": "GPT-4",
                "context": "128K tokens",
                "strengths": ["High quality", "Reasoning"],
                "best_for": "Complex analysis"
            }
        }
        return model_configs.get(model, {"name": model, "context": "Unknown", "strengths": [], "best_for": "Unknown"})

# Global instance
ai_provider = AIProviderManager()
