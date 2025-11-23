"""
Core Orchestrator - Central coordination of all trading modules

Responsibilities:
- Initialize and manage all strategy modules
- Allocate capital across strategies
- Coordinate inter-module communication
- Monitor system health
- Handle graceful shutdown
"""

import asyncio
import signal
from typing import Dict, Optional, Any
from datetime import datetime
import logging

from src.core.config import settings
from src.core.risk_manager import RiskManager
from src.utils.logger import get_logger
from src.data.storage.database import Database

# Strategy modules (will be imported as implemented)
# from src.modules.sniper.sniper_bot import SniperBot
# from src.modules.news_trader.news_trader import NewsTrader
# from src.modules.sentiment.sentiment_analyzer import SentimentAnalyzer
# from src.modules.ml_predictor.ml_predictor import MLPredictor
# from src.modules.arbitrage.arbitrage_engine import ArbitrageEngine
# from src.modules.defi_optimizer.defi_optimizer import DeFiOptimizer
# from src.modules.copy_trading.copy_trading import CopyTrader


logger = get_logger(__name__)


class Orchestrator:
    """
    Central orchestrator managing all trading strategies and system components
    """
    
    def __init__(self):
        """Initialize orchestrator"""
        self.logger = logger
        self.risk_manager = RiskManager()
        self.database: Optional[Database] = None
        
        # Strategy modules dictionary
        self.modules: Dict[str, Any] = {}
        
        # System state
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.total_trades = 0
        self.total_pnl = 0.0
        
        # Capital allocation (percentage per strategy)
        self.capital_allocation = {
            "sniper": 20.0,
            "news_trader": 25.0,
            "sentiment": 15.0,
            "ml_predictor": 15.0,
            "arbitrage": 15.0,
            "defi_optimizer": 5.0,
            "copy_trading": 5.0,
        }
        
        self.logger.info(f"[ORCHESTRATOR] Initialized - {settings.PROJECT_NAME} v{settings.VERSION}")
        self.logger.info(f"[INFO] Environment: {settings.ENVIRONMENT.value}")
        self.logger.info(f"[TEST] Testnet mode: {settings.USE_TESTNET}")
    
    async def initialize(self):
        """Initialize all system components"""
        self.logger.info("[INIT] Initializing system components...")
        
        try:
            # Initialize database
            self.database = Database()
            await self.database.connect()
            self.logger.info("[OK] Database connected")
            
            # Initialize risk manager
            await self.risk_manager.initialize()
            self.logger.info("[OK] Risk manager initialized")
            
            # Initialize strategy modules based on feature flags
            await self._initialize_modules()
            
            self.logger.info("[OK] All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Initialization failed: {e}")
            raise
    
    async def _initialize_modules(self):
        """Initialize enabled strategy modules"""
        self.logger.info("[MODULES] Initializing strategy modules...")
        
        # Module 1: Sniper Bot
        if settings.ENABLE_SNIPER:
            self.logger.info("   Sniper Bot: ENABLED")
            # self.modules["sniper"] = SniperBot()
            # await self.modules["sniper"].initialize()
            self.modules["sniper"] = None  # Placeholder until implemented
        
        # Module 2: News Trader
        if settings.ENABLE_NEWS_TRADER:
            self.logger.info("   News Trader: ENABLED")
            # self.modules["news_trader"] = NewsTrader()
            # await self.modules["news_trader"].initialize()
            self.modules["news_trader"] = None  # Placeholder
        
        # Module 3: Sentiment Analyzer
        if settings.ENABLE_SENTIMENT:
            self.logger.info("   Sentiment Analyzer: ENABLED")
            # self.modules["sentiment"] = SentimentAnalyzer()
            # await self.modules["sentiment"].initialize()
            self.modules["sentiment"] = None  # Placeholder
        
        # Module 4: ML Predictor
        if settings.ENABLE_ML_PREDICTOR:
            self.logger.info("   ML Predictor: ENABLED")
            # self.modules["ml_predictor"] = MLPredictor()
            # await self.modules["ml_predictor"].initialize()
            self.modules["ml_predictor"] = None  # Placeholder
        
        # Module 5: Arbitrage Engine
        if settings.ENABLE_ARBITRAGE:
            self.logger.info("   Arbitrage Engine: ENABLED")
            # self.modules["arbitrage"] = ArbitrageEngine()
            # await self.modules["arbitrage"].initialize()
            self.modules["arbitrage"] = None  # Placeholder
        
        # Module 6: DeFi Optimizer
        if settings.ENABLE_DEFI_OPTIMIZER:
            self.logger.info("   DeFi Optimizer: ENABLED")
            # self.modules["defi_optimizer"] = DeFiOptimizer()
            # await self.modules["defi_optimizer"].initialize()
            self.modules["defi_optimizer"] = None  # Placeholder
        
        # Module 7: Copy Trading
        if settings.ENABLE_COPY_TRADING:
            self.logger.info("   Copy Trading: ENABLED")
            # self.modules["copy_trading"] = CopyTrader()
            # await self.modules["copy_trading"].initialize()
            self.modules["copy_trading"] = None  # Placeholder
        
        enabled_count = len([m for m in self.modules.values() if m is not None])
        self.logger.info(f"[OK] {enabled_count} modules initialized")
    
    async def start(self):
        """Start the orchestrator and all modules"""
        self.logger.info("[START] Starting Cryptobot Ultimate...")
        
        try:
            # Initialize if not already done
            if self.database is None:
                await self.initialize()
            
            self.is_running = True
            self.start_time = datetime.utcnow()
            
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Start all enabled modules
            tasks = []
            for name, module in self.modules.items():
                if module is not None:
                    self.logger.info(f"[RUN]  Starting {name}...")
                    # task = asyncio.create_task(module.run())
                    # tasks.append(task)
            
            self.logger.info("[OK] All modules started")
            self.logger.info("[BOT] Cryptobot is now running!")
            
            # Main loop - monitor and coordinate
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"[ERROR] Fatal error: {e}")
            await self.stop()
            raise
    
    async def _main_loop(self):
        """Main orchestrator loop"""
        while self.is_running:
            try:
                # Monitor system health
                await self._health_check()
                
                # Update metrics
                await self._update_metrics()
                
                # Check risk limits
                await self.risk_manager.check_global_limits()
                
                # Sleep for a bit
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def _health_check(self):
        """Perform health check on all components"""
        # Check database connection
        if self.database:
            if not await self.database.is_healthy():
                self.logger.warning("[WARN]  Database health check failed")
        
        # Check each module
        for name, module in self.modules.items():
            if module is not None:
                # if not await module.is_healthy():
                #     self.logger.warning(f"[WARN]  {name} health check failed")
                pass
    
    async def _update_metrics(self):
        """Update system metrics"""
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            # Log metrics periodically
            if int(uptime) % 300 == 0:  # Every 5 minutes
                self.logger.info(f"[INFO] Uptime: {uptime/3600:.2f}h | Trades: {self.total_trades} | PnL: ${self.total_pnl:.2f}")
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            self.logger.info(f"[WARN]  Received signal {sig}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def stop(self):
        """Gracefully stop all modules and cleanup"""
        if not self.is_running:
            return
        
        self.logger.info("[STOP] Stopping Cryptobot...")
        self.is_running = False
        
        try:
            # Stop all modules
            for name, module in self.modules.items():
                if module is not None:
                    self.logger.info(f"[STOP]  Stopping {name}...")
                    # await module.stop()
            
            # Close database connection
            if self.database:
                await self.database.disconnect()
                self.logger.info("[OK] Database disconnected")
            
            # Final statistics
            if self.start_time:
                runtime = (datetime.utcnow() - self.start_time).total_seconds()
                self.logger.info(f"[INFO] Final Stats:")
                self.logger.info(f"   Runtime: {runtime/3600:.2f} hours")
                self.logger.info(f"   Total trades: {self.total_trades}")
                self.logger.info(f"   Total PnL: ${self.total_pnl:.2f}")
            
            self.logger.info("[OK] Shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current system status"""
        return {
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0,
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "enabled_modules": list(self.modules.keys()),
            "environment": settings.ENVIRONMENT.value,
            "testnet": settings.USE_TESTNET,
        }

