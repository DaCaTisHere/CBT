"""
Configuration Management using Pydantic Settings
Loads from environment variables and .env file
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional
from enum import Enum
import os


class Environment(str, Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """
    Main configuration class
    All settings loaded from environment variables or .env file
    """
    
    # ==========================================
    # GENERAL SETTINGS
    # ==========================================
    ENVIRONMENT: Environment = Field(default=Environment.DEVELOPMENT)
    LOG_LEVEL: LogLevel = Field(default=LogLevel.INFO)
    PROJECT_NAME: str = Field(default="Cryptobot Ultimate")
    VERSION: str = Field(default="0.1.0")
    
    # ==========================================
    # BLOCKCHAIN RPCs
    # ==========================================
    ETHEREUM_RPC_URL: Optional[str] = None
    ETHEREUM_TESTNET_RPC_URL: Optional[str] = None
    
    BSC_RPC_URL: str = Field(default="https://bsc-dataseed.binance.org/")
    BSC_TESTNET_RPC_URL: str = Field(default="https://data-seed-prebsc-1-s1.binance.org:8545/")
    
    ARBITRUM_RPC_URL: Optional[str] = None
    BASE_RPC_URL: Optional[str] = None
    
    # ==========================================
    # EXCHANGE APIs
    # ==========================================
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_SECRET: Optional[str] = None
    
    COINBASE_API_KEY: Optional[str] = None
    COINBASE_SECRET: Optional[str] = None
    
    # ==========================================
    # WALLET (CRITICAL - NEVER COMMIT!)
    # ==========================================
    WALLET_PRIVATE_KEY: str = Field(...)
    
    # ==========================================
    # DATABASE
    # ==========================================
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./cryptobot.db")
    
    # ==========================================
    # RISK MANAGEMENT
    # ==========================================
    MAX_POSITION_SIZE_PCT: float = Field(default=10.0, ge=0.0, le=100.0)
    MAX_DAILY_LOSS_PCT: float = Field(default=5.0, ge=0.0, le=100.0)
    STOP_LOSS_PCT: float = Field(default=15.0, ge=0.0)
    TAKE_PROFIT_PCT: float = Field(default=30.0, ge=0.0)
    MAX_SLIPPAGE_PCT: float = Field(default=2.0, ge=0.0, le=100.0)
    
    # ==========================================
    # FEATURE FLAGS (Enable/Disable Modules)
    # ==========================================
    ENABLE_SNIPER: bool = Field(default=False)
    ENABLE_NEWS_TRADER: bool = Field(default=True)
    ENABLE_SENTIMENT: bool = Field(default=False)
    ENABLE_ML_PREDICTOR: bool = Field(default=False)
    ENABLE_ARBITRAGE: bool = Field(default=False)
    ENABLE_DEFI_OPTIMIZER: bool = Field(default=False)
    ENABLE_COPY_TRADING: bool = Field(default=False)
    
    # News Trader sources (sub-features)
    ENABLE_BINANCE_NEWS: bool = Field(default=True)
    ENABLE_COINBASE_NEWS: bool = Field(default=True)
    ENABLE_TWITTER_NEWS: bool = Field(default=False)
    
    # ==========================================
    # EXTERNAL APIs (Optional)
    # ==========================================
    TWITTER_API_KEY: Optional[str] = None
    TWITTER_API_SECRET: Optional[str] = None
    TWITTER_BEARER_TOKEN: Optional[str] = None
    TWITTER_ACCESS_TOKEN: Optional[str] = None
    TWITTER_ACCESS_TOKEN_SECRET: Optional[str] = None
    TWITTER_CLIENT_ID: Optional[str] = None
    TWITTER_CLIENT_SECRET: Optional[str] = None
    
    TELEGRAM_API_ID: Optional[str] = None
    TELEGRAM_API_HASH: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    LUNARCRUSH_API_KEY: Optional[str] = None
    
    # ==========================================
    # OPENAI / AI OPTIMIZER
    # ==========================================
    OPENAI_API_KEY: Optional[str] = None
    ENABLE_AI_OPTIMIZER: bool = Field(default=False)
    AI_AUTO_APPLY_SUGGESTIONS: bool = Field(default=False)
    
    # ==========================================
    # SUPABASE (Analytics & Storage)
    # ==========================================
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    
    # ==========================================
    # ALERTS & WEBHOOKS
    # ==========================================
    WEBHOOK_URL: Optional[str] = None
    
    # ==========================================
    # TRADING MODES
    # ==========================================
    USE_TESTNET: bool = Field(default=True)
    SIMULATION_MODE: bool = Field(default=True)
    DRY_RUN: bool = Field(default=False)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }
    
    @validator("WALLET_PRIVATE_KEY")
    def validate_private_key(cls, v):
        """Validate private key format"""
        if not v.startswith("0x"):
            v = f"0x{v}"
        if len(v) != 66:  # 0x + 64 hex chars
            raise ValueError("Invalid private key length")
        return v
    
    @validator("MAX_POSITION_SIZE_PCT", "MAX_DAILY_LOSS_PCT")
    def validate_percentages(cls, v):
        """Ensure percentages are reasonable"""
        if v > 50:
            raise ValueError(f"Percentage too high: {v}%. Maximum recommended: 50%")
        return v
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    def is_testnet(self) -> bool:
        """Check if using testnet"""
        return self.USE_TESTNET or not self.is_production()


# Global settings instance
settings = Settings()

# ============================================================
# FORCE-READ critical trading mode from OS environment
# This bypasses any pydantic parsing issues with bool values
# ============================================================
def _parse_bool_env(name: str, default: bool) -> bool:
    """Explicitly parse bool from environment variable"""
    raw = os.getenv(name, "").strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    elif raw in ("true", "1", "yes", "on"):
        return True
    return default

_sim_parsed = _parse_bool_env("SIMULATION_MODE", settings.SIMULATION_MODE)
if settings.SIMULATION_MODE != _sim_parsed:
    settings.SIMULATION_MODE = _sim_parsed

_dry_parsed = _parse_bool_env("DRY_RUN", settings.DRY_RUN)
if settings.DRY_RUN != _dry_parsed:
    settings.DRY_RUN = _dry_parsed

_test_parsed = _parse_bool_env("USE_TESTNET", settings.USE_TESTNET)
if settings.USE_TESTNET != _test_parsed:
    settings.USE_TESTNET = _test_parsed

