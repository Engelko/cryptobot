from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices
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
    TRADING_SYMBOLS: Union[List[str], str] = Field(default=["BTCUSDT"], validation_alias=AliasChoices("TRADINGSYMBOLS", "TRADING_SYMBOLS"), description="List of symbols to trade")
    ACTIVE_STRATEGIES: Union[List[str], str] = Field(default=["MACD_Trend", "RSI_Reversion"], validation_alias=AliasChoices("ACTIVESTRATEGIES", "ACTIVE_STRATEGIES"), description="List of active strategies")

    # System Configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Risk Management - Core
    MAX_DAILY_LOSS: float = Field(50.0, gt=0, validation_alias=AliasChoices("MAXDAILYLOSS", "MAX_DAILY_LOSS"), description="Max daily loss in USDT")
    MAX_POSITION_SIZE: float = Field(100.0, gt=0, validation_alias=AliasChoices("MAXPOSITIONSIZE", "MAX_POSITION_SIZE"), description="Max position size in USDT")
    MAX_SINGLE_TRADE_LOSS: float = Field(30.0, gt=0, validation_alias=AliasChoices("MAXSINGLETRADELOSS", "MAX_SINGLE_TRADE_LOSS"), description="Max loss per single trade in USDT")
    MAX_LOSS_PER_EXIT: float = Field(5.0, gt=0, description="Max loss per emergency exit in USDT")
    MAX_LEVERAGE: float = Field(3.0, gt=0, validation_alias=AliasChoices("MAXLEVERAGE", "MAX_LEVERAGE"), description="Max leverage")
    DYNAMIC_LEVERAGE_ENABLED: bool = Field(False, description="Allow strategy-specified leverage above max")
    MAX_SPREAD: float = Field(0.001, description="Max allowed spread for liquidity check")
    
    # Risk Management - Stop Loss / Take Profit
    STOP_LOSS_PCT: float = Field(0.025, description="Hard stop loss percentage (2.5%)")
    TAKE_PROFIT_PCT: float = Field(0.03, description="Take profit percentage (3.0%)")
    TRAILING_STOP_TRIGGER: float = Field(0.03, description="Trailing stop activation profit percentage")
    MIN_HOLD_TIME: int = Field(60, gt=0, description="Minimum hold time in seconds before SL can trigger")
    
    # Risk Management - Cooldowns
    COOLDOWN_AFTER_LOSS: int = Field(900, gt=0, description="Cooldown in seconds after a loss (15 min)")
    COOLDOWN_AFTER_TRADE: int = Field(60, gt=0, description="Cooldown in seconds after any trade")
    
    # Risk Management - Drawdown
    INITIAL_DEPOSIT: float = Field(0.0, description="Initial deposit for drawdown tracking (set to 0.0 for auto-initialization from current balance)")
    RECOVERY_THRESHOLD: float = Field(0.70, description="Equity % to enter recovery mode")
    EMERGENCY_THRESHOLD: float = Field(0.50, description="Equity % for emergency stop")
    
    # Market Filters
    SESSION_BLACKLIST: Union[List[int], str] = Field(default=[16,17,18,19,20,21,22,23], description="UTC hours to block trading (American session)")
    MIN_ADX_ENTRY: float = Field(15.0, gt=0, description="Minimum ADX for entry signals")
    MAX_ATR_PCT: float = Field(0.05, gt=0, description="Max ATR as percentage of price")

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

    # Telegram Notifications
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot Token")
    TELEGRAM_CHAT_ID: str = Field(default="", description="Telegram Chat ID")

    # On-chain Analysis
    COINGECKO_API_KEY: str = Field(default="", description="CoinGecko API Key (Demo/Pro)")
    COINGECKO_PRO: bool = Field(default=False, description="Set to True if using CoinGecko Pro API")
    MESSARI_API_KEY: str = Field(default="", description="Messari API Key")
    ENABLE_ONCHAIN_FILTER: bool = Field(True, description="Enable On-chain score filtering")
    ONCHAIN_BUY_THRESHOLD: float = Field(0.3, description="Reject BUY if score < threshold")
    ONCHAIN_SELL_THRESHOLD: float = Field(0.7, description="Reject SELL if score > threshold")

    def model_post_init(self, __context):
        if isinstance(self.TRADING_SYMBOLS, str):
            try:
                self.TRADING_SYMBOLS = json.loads(self.TRADING_SYMBOLS)
            except:
                self.TRADING_SYMBOLS = [s.strip() for s in self.TRADING_SYMBOLS.split(",")]

        if isinstance(self.ACTIVE_STRATEGIES, str):
            try:
                self.ACTIVE_STRATEGIES = json.loads(self.ACTIVE_STRATEGIES)
            except:
                self.ACTIVE_STRATEGIES = [s.strip() for s in self.ACTIVE_STRATEGIES.split(",")]

        if isinstance(self.SESSION_BLACKLIST, str):
            try:
                self.SESSION_BLACKLIST = json.loads(self.SESSION_BLACKLIST)
            except:
                self.SESSION_BLACKLIST = [int(s.strip()) for s in self.SESSION_BLACKLIST.split(",")]

        if self.INITIAL_DEPOSIT == 0.0 and self.INITIAL_CAPITAL != 10000.0:
            self.INITIAL_DEPOSIT = self.INITIAL_CAPITAL

# Global Settings Instance
settings = Settings()
