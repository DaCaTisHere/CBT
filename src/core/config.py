"""
Configuration Management using Pydantic Settings
Loads from environment variables and .env file
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, List
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
    ETHEREUM_RPC_URL: str = Field(...)
    ETHEREUM_TESTNET_RPC_URL: Optional[str] = None
    
    SOLANA_RPC_URL: str = Field(default="https://api.mainnet-beta.solana.com")
    SOLANA_TESTNET_RPC_URL: str = Field(default="https://api.devnet.solana.com")
    
    BSC_RPC_URL: str = Field(default="https://bsc-dataseed.binance.org/")
    BSC_TESTNET_RPC_URL: str = Field(default="https://data-seed-prebsc-1-s1.binance.org:8545/")
    
    ARBITRUM_RPC_URL: Optional[str] = None
    BASE_RPC_URL: Optional[str] = None
    POLYGON_RPC_URL: Optional[str] = None
    
    # ==========================================
    # EXCHANGE APIs
    # ==========================================
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_SECRET: Optional[str] = None
    
    COINBASE_API_KEY: Optional[str] = None
    COINBASE_SECRET: Optional[str] = None
    
    KRAKEN_API_KEY: Optional[str] = None
    KRAKEN_SECRET: Optional[str] = None
    
    # ==========================================
    # WALLET (CRITICAL - NEVER COMMIT!)
    # ==========================================
    WALLET_PRIVATE_KEY: str = Field(...)
    WALLET_ADDRESS: Optional[str] = None
    
    # ==========================================
    # DATABASE
    # ==========================================
    DATABASE_URL: str = Field(default="sqlite:///./cryptobot.db")  # Use SQLite by default for Railway
    REDIS_URL: Optional[str] = Field(default=None)  # Optional for Railway
    RABBITMQ_URL: Optional[str] = Field(default=None)  # Optional for Railway
    
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
    ENABLE_SNIPER: bool = Field(default=True)
    ENABLE_NEWS_TRADER: bool = Field(default=True)
    ENABLE_SENTIMENT: bool = Field(default=False)
    ENABLE_ML_PREDICTOR: bool = Field(default=False)
    ENABLE_ARBITRAGE: bool = Field(default=False)
    ENABLE_DEFI_OPTIMIZER: bool = Field(default=False)
    ENABLE_COPY_TRADING: bool = Field(default=False)
    
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
    
    LUNARCRUSH_API_KEY: Optional[str] = None
    SANTIMENT_API_KEY: Optional[str] = None
    NANSEN_API_KEY: Optional[str] = None
    
    # ==========================================
    # MONITORING
    # ==========================================
    SENTRY_DSN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    # ==========================================
    # TRADING MODES
    # ==========================================
    USE_TESTNET: bool = Field(default=True)
    SIMULATION_MODE: bool = Field(default=False)
    DRY_RUN: bool = Field(default=False)
    
    # ==========================================
    # PERFORMANCE
    # ==========================================
    MAX_WORKERS: int = Field(default=4, ge=1)
    ENABLE_CACHING: bool = Field(default=True)
    CACHE_TTL_SECONDS: int = Field(default=60)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
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

