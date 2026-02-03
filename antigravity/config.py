from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal, List, Union
import json

class Settings(BaseSettings):
    """
    Application Configuration
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Bybit API Credentials
    BYBIT_API_KEY: str = Field(default="", description="Bybit API Public Key")
    BYBIT_API_SECRET: str = Field(default="", description="Bybit API Secret Key")
    BYBIT_TESTNET: bool = Field(True, description="Use Testnet if True")

    # Trading Configuration
    TRADING_SYMBOLS: Union[List[str], str] = Field(default=["BTCUSDT"], description="List of symbols to trade")
    ACTIVE_STRATEGIES: Union[List[str], str] = Field(default=["MACD_Trend", "RSI_Reversion"], description="List of active strategies")

    # System Configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Risk Management
    MAX_DAILY_LOSS: float = Field(20.0, gt=0, description="Max daily loss in USDT")
    MAX_POSITION_SIZE: float = Field(50.0, gt=0, description="Max position size in USDT")
    MAX_LEVERAGE: float = Field(3.0, gt=0, description="Max leverage")
    STOP_LOSS_PCT: float = Field(0.02, description="Hard stop loss percentage")
    TRAILING_STOP_TRIGGER: float = Field(0.015, description="Trailing stop activation profit percentage")
    INITIAL_DEPOSIT: float = Field(186.0, description="Initial deposit for drawdown tracking")
    RECOVERY_THRESHOLD: float = Field(0.70, description="Equity % to enter recovery mode")
    EMERGENCY_THRESHOLD: float = Field(0.50, description="Equity % for emergency stop")

    # AI / LLM Configuration
    LLM_API_KEY: str = Field(default="", description="API Key for LLM Provider")
    LLM_BASE_URL: str = Field(default="https://api.deepseek.com/v1", description="Base URL for LLM API")
    LLM_MODEL: str = Field(default="deepseek-chat", description="Model Name")

    # Simulation Mode
    SIMULATION_MODE: bool = Field(False, description="Enable Paper Trading")
    INITIAL_CAPITAL: float = Field(10000.0, description="Initial Paper Trading Capital (USDT)")

    # Machine Learning
    ENABLE_ML: bool = Field(True, description="Enable ML Engine")

    # Security
    AUDIT_ENABLED: bool = Field(True, description="Enable Audit Logging")

    # Database
    DATABASE_URL: str = Field("sqlite:///storage/data.db", description="Database URL")

    def model_post_init(self, __context):
        # Handle string input for list if coming from .env as a string
        if isinstance(self.TRADING_SYMBOLS, str):
            try:
                self.TRADING_SYMBOLS = json.loads(self.TRADING_SYMBOLS)
            except:
                # Fallback: split by comma if not valid JSON
                self.TRADING_SYMBOLS = [s.strip() for s in self.TRADING_SYMBOLS.split(",")]

        if isinstance(self.ACTIVE_STRATEGIES, str):
            try:
                self.ACTIVE_STRATEGIES = json.loads(self.ACTIVE_STRATEGIES)
            except:
                self.ACTIVE_STRATEGIES = [s.strip() for s in self.ACTIVE_STRATEGIES.split(",")]

# Global Settings Instance
settings = Settings()
