"""Arbitrage Engine - Multi-exchange price differences"""

import asyncio
from typing import Dict, Any
from src.core.risk_manager import RiskManager
from src.execution.order_engine import OrderEngine
from src.utils.logger import get_logger

logger = get_logger(__name__)

class ArbitrageEngine:
    def __init__(self, risk_manager: RiskManager, order_engine: OrderEngine):
        self.logger = logger
        self.risk_manager = risk_manager
        self.order_engine = order_engine
        self.is_running = False
        self.arbitrages_found = 0
        self.logger.info("⚡ Arbitrage Engine initialized")
    
    async def initialize(self):
        self.logger.info("[OK] Arbitrage Engine ready")
    
    async def run(self):
        self.is_running = True
        self.logger.info("[RUN]  Arbitrage Engine scanning...")
        while self.is_running:
            # Scan for price differences
            await asyncio.sleep(5)
    
    async def stop(self):
        self.is_running = False
        self.logger.info(f"[STOP]  Arbitrage stopped ({self.arbitrages_found} found)")
    
    async def is_healthy(self) -> bool:
        return self.is_running
    
    async def get_stats(self) -> Dict[str, Any]:
        return {"arbitrages_found": self.arbitrages_found}

