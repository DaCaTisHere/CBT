"""
Pool Detector - Detects new and trending pools for trading

Scans multiple chains for:
- Newly created pools (sniper opportunities)
- Trending pools (momentum plays)
- High volume pools (liquidity confirmation)
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.modules.geckoterminal.gecko_client import GeckoTerminalClient, Pool
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PoolSignal:
    """Trading signal from pool detection"""
    pool: Pool
    signal_type: str  # "new_pool", "trending", "volume_spike"
    score: float  # 0-100
    reasons: List[str]
    timestamp: datetime


class PoolDetector:
    """
    Detects tradeable pools across multiple chains
    
    Strategies:
    1. NEW POOL: Early entry on newly created pools
    2. TRENDING: Momentum on pools gaining volume
    3. VOLUME SPIKE: Sudden liquidity increase
    """
    
    # Chains to monitor (prioritized by opportunity)
    PRIORITY_CHAINS = ["solana", "base", "eth", "arbitrum", "bsc"]
    
    # Filters for new pools
    MIN_LIQUIDITY_USD = 10000      # $10k minimum liquidity
    MAX_LIQUIDITY_USD = 5000000    # $5M max (avoid whales)
    MIN_VOLUME_24H = 5000          # $5k minimum volume
    MIN_TRANSACTIONS_24H = 50      # At least 50 trades
    MIN_BUY_RATIO = 0.4            # At least 40% buys
    
    # Filters for trending
    MIN_PRICE_CHANGE_24H = 10      # At least +10% in 24h
    MAX_PRICE_CHANGE_24H = 500     # Not too extreme (< 500%)
    
    def __init__(self):
        self.logger = logger
        self.client = GeckoTerminalClient()
        self.is_running = False
        
        # Tracking
        self.seen_pools: Dict[str, datetime] = {}  # pool_address -> first_seen
        self.signals: List[PoolSignal] = []
        self.signal_callbacks: List[Callable] = []
        
        # Stats
        self.pools_scanned = 0
        self.signals_generated = 0
        
    async def initialize(self):
        """Initialize the detector"""
        await self.client.initialize()
        self.logger.info("[POOL] Pool Detector initialized")
        
    async def close(self):
        """Close the detector"""
        self.is_running = False
        await self.client.close()
        
    def on_signal(self, callback: Callable):
        """Register callback for new signals"""
        self.signal_callbacks.append(callback)
        
    async def _emit_signal(self, signal: PoolSignal):
        """Emit signal to all callbacks"""
        self.signals.append(signal)
        self.signals_generated += 1
        
        for callback in self.signal_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(signal)
                else:
                    callback(signal)
            except Exception as e:
                self.logger.error(f"[POOL] Callback error: {e}")
                
    async def start(self):
        """Start pool detection loop"""
        self.is_running = True
        self.logger.info("[POOL] Starting pool detection...")
        self.logger.info(f"[POOL] Monitoring chains: {', '.join(self.PRIORITY_CHAINS)}")
        
        while self.is_running:
            try:
                for chain in self.PRIORITY_CHAINS:
                    if not self.is_running:
                        break
                        
                    # Scan new pools
                    await self._scan_new_pools(chain)
                    
                    # Scan trending pools
                    await self._scan_trending_pools(chain)
                    
                    # Small delay between chains
                    await asyncio.sleep(2)
                    
                # Wait before next scan cycle
                await asyncio.sleep(30)  # Scan every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[POOL] Scan error: {e}")
                await asyncio.sleep(10)
                
    async def _scan_new_pools(self, chain: str):
        """Scan for new pools on a chain"""
        try:
            pools = await self.client.get_new_pools(chain, limit=20)
            self.pools_scanned += len(pools)
            
            for pool in pools:
                # Skip if already seen
                if pool.address in self.seen_pools:
                    continue
                    
                # Mark as seen
                self.seen_pools[pool.address] = datetime.utcnow()
                
                # Score the pool
                score, reasons = self._score_new_pool(pool)
                
                if score >= 60:
                    signal = PoolSignal(
                        pool=pool,
                        signal_type="new_pool",
                        score=score,
                        reasons=reasons,
                        timestamp=datetime.utcnow()
                    )
                    
                    self.logger.info(f"[POOL] 🆕 NEW POOL DETECTED on {chain.upper()}")
                    self.logger.info(f"[POOL]    {pool.base_token}/{pool.quote_token} on {pool.dex}")
                    self.logger.info(f"[POOL]    Price: ${pool.price_usd:.8f} | Liq: ${pool.liquidity_usd:,.0f}")
                    self.logger.info(f"[POOL]    Score: {score:.0f}/100 | {', '.join(reasons)}")
                    
                    await self._emit_signal(signal)
                    
        except Exception as e:
            self.logger.error(f"[POOL] New pool scan error on {chain}: {e}")
            
    async def _scan_trending_pools(self, chain: str):
        """Scan for trending pools on a chain"""
        try:
            pools = await self.client.get_trending_pools(chain, limit=20)
            self.pools_scanned += len(pools)
            
            for pool in pools:
                # Score the pool
                score, reasons = self._score_trending_pool(pool)
                
                # Avoid re-signaling same pool too often
                cache_key = f"trending_{pool.address}"
                if cache_key in self.seen_pools:
                    last_signal = self.seen_pools[cache_key]
                    if datetime.utcnow() - last_signal < timedelta(hours=1):
                        continue
                        
                if score >= 70:
                    self.seen_pools[cache_key] = datetime.utcnow()
                    
                    signal = PoolSignal(
                        pool=pool,
                        signal_type="trending",
                        score=score,
                        reasons=reasons,
                        timestamp=datetime.utcnow()
                    )
                    
                    self.logger.info(f"[POOL] 🔥 TRENDING POOL on {chain.upper()}")
                    self.logger.info(f"[POOL]    {pool.base_token}/{pool.quote_token}")
                    self.logger.info(f"[POOL]    24h: {pool.price_change_24h:+.1f}% | Vol: ${pool.volume_24h:,.0f}")
                    self.logger.info(f"[POOL]    Score: {score:.0f}/100")
                    
                    await self._emit_signal(signal)
                    
        except Exception as e:
            self.logger.error(f"[POOL] Trending scan error on {chain}: {e}")
            
    def _score_new_pool(self, pool: Pool) -> tuple[float, List[str]]:
        """
        Score a new pool for trading potential
        
        Returns:
            (score 0-100, list of reasons)
        """
        score = 0
        reasons = []
        
        # 1. Liquidity check (0-25 points)
        if pool.liquidity_usd >= self.MIN_LIQUIDITY_USD:
            if pool.liquidity_usd >= 100000:
                score += 25
                reasons.append("Strong liquidity")
            elif pool.liquidity_usd >= 50000:
                score += 20
                reasons.append("Good liquidity")
            else:
                score += 15
                reasons.append("OK liquidity")
        else:
            return 0, ["Liquidity too low"]
            
        # 2. Volume check (0-20 points)
        if pool.volume_24h >= self.MIN_VOLUME_24H:
            if pool.volume_24h >= 50000:
                score += 20
                reasons.append("High volume")
            elif pool.volume_24h >= 20000:
                score += 15
            else:
                score += 10
        else:
            score -= 10
            
        # 3. Transaction count (0-15 points)
        if pool.transactions_24h >= self.MIN_TRANSACTIONS_24H:
            if pool.transactions_24h >= 200:
                score += 15
                reasons.append("Very active")
            elif pool.transactions_24h >= 100:
                score += 10
            else:
                score += 5
                
        # 4. Buy/Sell ratio (0-20 points)
        total_trades = pool.buys_24h + pool.sells_24h
        if total_trades > 0:
            buy_ratio = pool.buys_24h / total_trades
            if buy_ratio >= 0.6:
                score += 20
                reasons.append("Strong buying pressure")
            elif buy_ratio >= self.MIN_BUY_RATIO:
                score += 10
            else:
                score -= 10
                reasons.append("More sells than buys")
                
        # 5. Price action (0-20 points)
        if 0 < pool.price_change_24h <= 100:
            score += 15
            reasons.append(f"+{pool.price_change_24h:.0f}% 24h")
        elif pool.price_change_24h > 100:
            score += 10  # Too much pump can be risky
            reasons.append("Large pump (caution)")
        elif pool.price_change_24h < -20:
            score -= 15
            reasons.append("Dumping")
            
        return max(0, min(100, score)), reasons
        
    def _score_trending_pool(self, pool: Pool) -> tuple[float, List[str]]:
        """
        Score a trending pool for momentum trading
        
        Returns:
            (score 0-100, list of reasons)
        """
        score = 0
        reasons = []
        
        # 1. Must have minimum liquidity
        if pool.liquidity_usd < 50000:
            return 0, ["Low liquidity"]
            
        # 2. Price change score (0-30 points)
        change = pool.price_change_24h
        if self.MIN_PRICE_CHANGE_24H <= change <= 50:
            score += 30
            reasons.append(f"Healthy pump +{change:.0f}%")
        elif 50 < change <= 100:
            score += 25
            reasons.append(f"Strong pump +{change:.0f}%")
        elif 100 < change <= self.MAX_PRICE_CHANGE_24H:
            score += 15
            reasons.append(f"Extreme pump +{change:.0f}% (caution)")
        elif change < self.MIN_PRICE_CHANGE_24H:
            return 0, ["Not enough momentum"]
        else:
            return 0, ["Pump too extreme"]
            
        # 3. Volume confirmation (0-25 points)
        if pool.volume_24h >= 100000:
            score += 25
            reasons.append("Very high volume")
        elif pool.volume_24h >= 50000:
            score += 20
        elif pool.volume_24h >= 20000:
            score += 15
        else:
            score += 5
            
        # 4. Liquidity score (0-20 points)
        if pool.liquidity_usd >= 500000:
            score += 20
            reasons.append("Deep liquidity")
        elif pool.liquidity_usd >= 200000:
            score += 15
        elif pool.liquidity_usd >= 100000:
            score += 10
        else:
            score += 5
            
        # 5. Activity score (0-15 points)
        if pool.transactions_24h >= 500:
            score += 15
            reasons.append("Very active")
        elif pool.transactions_24h >= 200:
            score += 10
        elif pool.transactions_24h >= 100:
            score += 5
            
        # 6. Buy pressure bonus (0-10 points)
        total = pool.buys_24h + pool.sells_24h
        if total > 0:
            buy_ratio = pool.buys_24h / total
            if buy_ratio >= 0.55:
                score += 10
                reasons.append("Buying > Selling")
                
        return max(0, min(100, score)), reasons
        
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        return {
            "pools_scanned": self.pools_scanned,
            "signals_generated": self.signals_generated,
            "chains_monitored": len(self.PRIORITY_CHAINS),
            "pools_tracked": len(self.seen_pools)
        }
