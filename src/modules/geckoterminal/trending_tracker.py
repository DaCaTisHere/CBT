"""
Trending Tracker - Simplified wrapper for trending pool signals

Provides easy access to trending opportunities across chains.
"""

from typing import List, Dict, Any
from src.modules.geckoterminal.gecko_client import GeckoTerminalClient, Pool
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TrendingTracker:
    """
    Tracks trending tokens across multiple chains
    
    Provides:
    - Top trending by volume
    - Top gainers by price
    - Best opportunities (combined score)
    """
    
    CHAINS = ["solana", "base", "eth", "arbitrum"]
    
    def __init__(self):
        self.client = GeckoTerminalClient()
        self.logger = logger
        
    async def initialize(self):
        await self.client.initialize()
        
    async def close(self):
        await self.client.close()
        
    async def get_top_opportunities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top trading opportunities across all chains
        
        Returns list of opportunities sorted by score
        """
        opportunities = []
        
        for chain in self.CHAINS:
            try:
                trending = await self.client.get_trending_pools(chain, limit=10)
                
                for pool in trending:
                    # Calculate opportunity score
                    score = self._calculate_opportunity_score(pool)
                    
                    if score >= 50:
                        opportunities.append({
                            "chain": chain,
                            "symbol": pool.base_token,
                            "pool_address": pool.address,
                            "dex": pool.dex,
                            "price_usd": pool.price_usd,
                            "price_change_24h": pool.price_change_24h,
                            "volume_24h": pool.volume_24h,
                            "liquidity_usd": pool.liquidity_usd,
                            "score": score
                        })
                        
            except Exception as e:
                self.logger.error(f"Error fetching {chain}: {e}")
                
        # Sort by score descending
        opportunities.sort(key=lambda x: x["score"], reverse=True)
        
        return opportunities[:limit]
        
    def _calculate_opportunity_score(self, pool: Pool) -> float:
        """Calculate opportunity score (0-100)"""
        score = 0
        
        # Price momentum (0-40)
        change = pool.price_change_24h
        if 10 <= change <= 50:
            score += 40
        elif 50 < change <= 100:
            score += 30
        elif 5 <= change < 10:
            score += 20
        elif change > 100:
            score += 10  # Too pumped
            
        # Volume confirmation (0-30)
        if pool.volume_24h >= 100000:
            score += 30
        elif pool.volume_24h >= 50000:
            score += 25
        elif pool.volume_24h >= 20000:
            score += 15
        elif pool.volume_24h >= 10000:
            score += 10
            
        # Liquidity safety (0-30)
        if pool.liquidity_usd >= 200000:
            score += 30
        elif pool.liquidity_usd >= 100000:
            score += 25
        elif pool.liquidity_usd >= 50000:
            score += 15
        elif pool.liquidity_usd >= 20000:
            score += 10
            
        return min(100, score)
        
    async def get_new_gems(self, chain: str = "solana", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Find new potential gems on a specific chain
        
        Args:
            chain: Network to scan
            limit: Number of gems to return
            
        Returns:
            List of potential gems
        """
        gems = []
        
        try:
            new_pools = await self.client.get_new_pools(chain, limit=30)
            
            for pool in new_pools:
                # Filter criteria for gems
                if pool.liquidity_usd < 10000:
                    continue
                if pool.volume_24h < 5000:
                    continue
                if pool.transactions_24h < 30:
                    continue
                    
                # Calculate gem score
                score = 0
                
                # Early entry bonus
                if pool.liquidity_usd < 100000:
                    score += 20
                    
                # Volume relative to liquidity (activity)
                if pool.liquidity_usd > 0:
                    vol_ratio = pool.volume_24h / pool.liquidity_usd
                    if vol_ratio >= 1:
                        score += 30  # High activity
                    elif vol_ratio >= 0.5:
                        score += 20
                    elif vol_ratio >= 0.2:
                        score += 10
                        
                # Buy pressure
                total = pool.buys_24h + pool.sells_24h
                if total > 0:
                    buy_ratio = pool.buys_24h / total
                    if buy_ratio >= 0.6:
                        score += 30
                    elif buy_ratio >= 0.5:
                        score += 15
                        
                # Price action
                if 0 < pool.price_change_24h <= 50:
                    score += 20
                    
                if score >= 40:
                    gems.append({
                        "chain": chain,
                        "symbol": pool.base_token,
                        "pool_address": pool.address,
                        "price_usd": pool.price_usd,
                        "price_change_24h": pool.price_change_24h,
                        "volume_24h": pool.volume_24h,
                        "liquidity_usd": pool.liquidity_usd,
                        "buy_ratio": pool.buys_24h / max(1, pool.buys_24h + pool.sells_24h),
                        "gem_score": score
                    })
                    
        except Exception as e:
            self.logger.error(f"Error finding gems on {chain}: {e}")
            
        # Sort by gem score
        gems.sort(key=lambda x: x["gem_score"], reverse=True)
        
        return gems[:limit]
