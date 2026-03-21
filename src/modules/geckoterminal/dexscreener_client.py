"""
DexScreener API Client - Fallback for GeckoTerminal

Much more generous rate limits (300 req/min vs 30 for Gecko).
No API key required.

API Docs: https://docs.dexscreener.com/api/reference
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.modules.geckoterminal.gecko_client import Pool
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Chain ID mapping for DexScreener
CHAIN_MAP = {
    "bsc": "bsc",
    "base": "base",
    "eth": "ethereum",
    "arbitrum": "arbitrum",
    "polygon_pos": "polygon",
    "avax": "avalanche",
    "solana": "solana",
}

CHAIN_MAP_REVERSE = {v: k for k, v in CHAIN_MAP.items()}


class DexScreenerClient:
    """
    Async client for DexScreener API
    
    Used as fallback when GeckoTerminal is rate-limited.
    """
    
    BASE_URL = "https://api.dexscreener.com"
    
    def __init__(self):
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self):
        """Initialize the HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={
                "Accept": "application/json",
                "User-Agent": "CryptobotUltimate/1.0",
            },
            timeout=aiohttp.ClientTimeout(total=15)
        )
        self.logger.info("[DEXSCREENER] Client initialized")
        
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
    
    async def _get(self, url: str) -> Optional[Dict]:
        """Make GET request"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.warning(f"[DEXSCREENER] API error: {response.status}")
                    return None
        except asyncio.TimeoutError:
            self.logger.debug("[DEXSCREENER] Request timeout")
            return None
        except Exception as e:
            self.logger.error(f"[DEXSCREENER] Request error: {e}")
            return None
    
    async def get_latest_token_profiles(self) -> List[Pool]:
        """
        Get latest token profiles from DexScreener.
        These are newly listed/profiled tokens across all chains.
        """
        url = f"{self.BASE_URL}/token-profiles/latest/v1"
        data = await self._get(url)
        
        if not data or not isinstance(data, list):
            return []
        
        pools = []
        for item in data[:30]:  # Limit to 30 latest
            try:
                chain_id = item.get("chainId", "")
                token_address = item.get("tokenAddress", "")
                
                # Map to our network IDs
                network = CHAIN_MAP_REVERSE.get(chain_id, chain_id)
                
                if token_address and chain_id:
                    pools.append(Pool(
                        address=token_address,
                        name=item.get("description", "New Token")[:50],
                        network=network,
                        dex="dexscreener",
                        base_token=item.get("header", token_address[:10]),
                        quote_token="USD",
                        price_usd=0,  # Will be enriched later
                        price_change_24h=0,
                        volume_24h=0,
                        liquidity_usd=0,
                        fdv_usd=0,
                        market_cap_usd=0,
                    ))
            except Exception:
                continue
        
        return pools
    
    async def get_latest_boosted_tokens(self) -> List[Pool]:
        """
        Get latest boosted tokens (trending/promoted).
        """
        url = f"{self.BASE_URL}/token-boosts/latest/v1"
        data = await self._get(url)
        
        if not data or not isinstance(data, list):
            return []
        
        pools = []
        for item in data[:20]:
            try:
                chain_id = item.get("chainId", "")
                token_address = item.get("tokenAddress", "")
                network = CHAIN_MAP_REVERSE.get(chain_id, chain_id)
                
                if token_address and chain_id:
                    pools.append(Pool(
                        address=token_address,
                        name=item.get("description", "Boosted Token")[:50],
                        network=network,
                        dex="dexscreener-boost",
                        base_token=item.get("header", token_address[:10]),
                        quote_token="USD",
                        price_usd=0,
                        price_change_24h=0,
                        volume_24h=0,
                        liquidity_usd=0,
                        fdv_usd=0,
                        market_cap_usd=0,
                    ))
            except Exception:
                continue
        
        return pools
    
    async def get_token_pairs(self, token_address: str) -> List[Dict]:
        """
        Get all pairs for a token address.
        Returns full pair data with liquidity, volume, price changes.
        """
        url = f"{self.BASE_URL}/latest/dex/tokens/{token_address}"
        data = await self._get(url)
        
        if not data:
            return []
        
        return data.get("pairs", [])
    
    async def enrich_pool(self, pool: Pool) -> Pool:
        """
        Enrich a pool with full data from DexScreener pairs endpoint.
        """
        pairs = await self.get_token_pairs(pool.address)
        
        if not pairs:
            return pool
        
        # Get the most liquid pair
        best_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        
        try:
            pool.price_usd = float(best_pair.get("priceUsd", 0) or 0)
            pool.liquidity_usd = float(best_pair.get("liquidity", {}).get("usd", 0) or 0)
            pool.volume_24h = float(best_pair.get("volume", {}).get("h24", 0) or 0)
            pool.fdv_usd = float(best_pair.get("fdv", 0) or 0)
            pool.market_cap_usd = float(best_pair.get("marketCap", 0) or 0)
            
            price_change = best_pair.get("priceChange", {})
            pool.price_change_24h = float(price_change.get("h24", 0) or 0)
            
            txns = best_pair.get("txns", {}).get("h24", {})
            pool.buys_24h = int(txns.get("buys", 0) or 0)
            pool.sells_24h = int(txns.get("sells", 0) or 0)
            pool.transactions_24h = pool.buys_24h + pool.sells_24h
            
            pool.base_token = best_pair.get("baseToken", {}).get("symbol", pool.base_token)
            pool.quote_token = best_pair.get("quoteToken", {}).get("symbol", pool.quote_token)
            pool.dex = best_pair.get("dexId", pool.dex)
            pool.name = f"{pool.base_token}/{pool.quote_token}"
            
            pool.token_address = best_pair.get("baseToken", {}).get("address", pool.address)
            
        except Exception as e:
            self.logger.debug(f"[DEXSCREENER] Enrich error: {e}")
        
        return pool
    
    async def get_top_boosted_tokens(self) -> List[Pool]:
        """
        Get TOP boosted tokens (highest boost amounts).
        Different from latest - returns most promoted tokens.
        """
        url = f"{self.BASE_URL}/token-boosts/top/v1"
        data = await self._get(url)
        
        if not data or not isinstance(data, list):
            return []
        
        pools = []
        for item in data[:30]:
            try:
                chain_id = item.get("chainId", "")
                token_address = item.get("tokenAddress", "")
                network = CHAIN_MAP_REVERSE.get(chain_id, chain_id)
                
                if token_address and chain_id:
                    pools.append(Pool(
                        address=token_address,
                        name=item.get("description", "Top Boosted")[:50],
                        network=network,
                        dex="dexscreener-top",
                        base_token=item.get("header", token_address[:10]),
                        quote_token="USD",
                        price_usd=0,
                        price_change_24h=0,
                        volume_24h=0,
                        liquidity_usd=0,
                        fdv_usd=0,
                        market_cap_usd=0,
                    ))
            except Exception:
                continue
        
        return pools

    async def search_pairs(self, query: str) -> List[Pool]:
        """
        Search for pairs by name/symbol.
        """
        url = f"{self.BASE_URL}/latest/dex/search?q={query}"
        data = await self._get(url)
        
        if not data:
            return []
        
        pools = []
        for pair in data.get("pairs", [])[:20]:
            try:
                chain_id = pair.get("chainId", "")
                network = CHAIN_MAP_REVERSE.get(chain_id, chain_id)
                
                pools.append(Pool(
                    address=pair.get("baseToken", {}).get("address", ""),
                    name=pair.get("baseToken", {}).get("name", "Unknown"),
                    network=network,
                    dex=pair.get("dexId", "unknown"),
                    base_token=pair.get("baseToken", {}).get("symbol", ""),
                    quote_token=pair.get("quoteToken", {}).get("symbol", ""),
                    price_usd=float(pair.get("priceUsd", 0) or 0),
                    price_change_24h=float(pair.get("priceChange", {}).get("h24", 0) or 0),
                    volume_24h=float(pair.get("volume", {}).get("h24", 0) or 0),
                    liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0) or 0),
                    fdv_usd=float(pair.get("fdv", 0) or 0),
                    market_cap_usd=float(pair.get("marketCap", 0) or 0),
                    buys_24h=int(pair.get("txns", {}).get("h24", {}).get("buys", 0) or 0),
                    sells_24h=int(pair.get("txns", {}).get("h24", {}).get("sells", 0) or 0),
                    transactions_24h=int(pair.get("txns", {}).get("h24", {}).get("buys", 0) or 0) + int(pair.get("txns", {}).get("h24", {}).get("sells", 0) or 0),
                ))
            except Exception:
                continue
        
        return pools
    
    async def search_pairs_on_chain(self, query: str, target_chains: List[str]) -> List[Pool]:
        """
        Search for pairs and filter by target chains.
        More efficient way to find tokens on specific networks.
        """
        all_pools = await self.search_pairs(query)
        return [p for p in all_pools if p.network in target_chains]
