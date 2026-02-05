"""
GeckoTerminal API Client

Free API access to real-time DEX data across 200+ chains.
No API key required!

API Docs: https://api.geckoterminal.com/docs
Rate Limit: 30 calls/minute (free tier)
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Pool:
    """Represents a DEX liquidity pool"""
    address: str
    name: str
    network: str
    dex: str
    base_token: str
    quote_token: str
    price_usd: float
    price_change_24h: float
    volume_24h: float
    liquidity_usd: float
    fdv_usd: float
    market_cap_usd: float
    created_at: Optional[datetime] = None
    transactions_24h: int = 0
    buys_24h: int = 0
    sells_24h: int = 0


@dataclass
class Token:
    """Represents a token on a DEX"""
    address: str
    symbol: str
    name: str
    network: str
    price_usd: float
    price_change_24h: float
    volume_24h: float
    fdv_usd: float


class GeckoTerminalClient:
    """
    Async client for GeckoTerminal API
    
    Features:
    - New pool detection
    - Trending pools
    - Token prices
    - OHLCV data
    """
    
    BASE_URL = "https://api.geckoterminal.com/api/v2"
    
    # Supported networks (most active)
    NETWORKS = {
        "eth": "ethereum",
        "solana": "solana", 
        "base": "base",
        "arbitrum": "arbitrum",
        "bsc": "bsc",
        "polygon_pos": "polygon",
        "avalanche": "avalanche",
        "optimism": "optimism"
    }
    
    # Rate limiting
    RATE_LIMIT_CALLS = 30
    RATE_LIMIT_PERIOD = 60  # seconds
    
    def __init__(self):
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        self._call_times: List[datetime] = []
        self._cache: Dict[str, tuple] = {}  # (data, timestamp)
        self._cache_ttl = 60  # seconds - increased to reduce API calls
        
    async def initialize(self):
        """Initialize the client"""
        self.session = aiohttp.ClientSession(
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self.logger.info("[GECKO] GeckoTerminal client initialized")
        
    async def close(self):
        """Close the client"""
        if self.session:
            await self.session.close()
            
    async def _rate_limit(self):
        """Enforce rate limiting"""
        now = datetime.utcnow()
        
        # Remove old calls
        self._call_times = [t for t in self._call_times 
                          if now - t < timedelta(seconds=self.RATE_LIMIT_PERIOD)]
        
        # Wait if at limit
        if len(self._call_times) >= self.RATE_LIMIT_CALLS:
            wait_time = (self._call_times[0] + timedelta(seconds=self.RATE_LIMIT_PERIOD) - now).total_seconds()
            if wait_time > 0:
                self.logger.debug(f"[GECKO] Rate limit - waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        
        self._call_times.append(now)
        
    def _get_cache(self, key: str) -> Optional[Any]:
        """Get cached data if still valid"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self._cache_ttl):
                return data
        return None
        
    def _set_cache(self, key: str, data: Any):
        """Cache data"""
        self._cache[key] = (data, datetime.utcnow())
        
    async def _get(self, endpoint: str) -> Optional[Dict]:
        """Make GET request with rate limiting and caching"""
        # Check cache first
        cached = self._get_cache(endpoint)
        if cached:
            return cached
            
        await self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}{endpoint}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self._set_cache(endpoint, data)
                    return data
                elif response.status == 429:
                    self.logger.warning("[GECKO] Rate limited - backing off")
                    await asyncio.sleep(60)
                    return None
                else:
                    self.logger.warning(f"[GECKO] API error: {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"[GECKO] Request error: {e}")
            return None
            
    # ==================== NETWORKS ====================
    
    async def get_networks(self) -> List[str]:
        """Get list of supported networks"""
        data = await self._get("/networks")
        if not data:
            return []
        return [n["id"] for n in data.get("data", [])]
        
    # ==================== NEW POOLS ====================
    
    async def get_new_pools(self, network: str = "eth", limit: int = 20) -> List[Pool]:
        """
        Get newest pools on a network
        
        Args:
            network: Network ID (eth, solana, base, etc.)
            limit: Number of pools to return
            
        Returns:
            List of new Pool objects
        """
        endpoint = f"/networks/{network}/new_pools"
        data = await self._get(endpoint)
        
        if not data:
            return []
            
        pools = []
        for item in data.get("data", [])[:limit]:
            try:
                attrs = item.get("attributes", {})
                pools.append(Pool(
                    address=attrs.get("address", ""),
                    name=attrs.get("name", "Unknown"),
                    network=network,
                    dex=attrs.get("dex_id", "unknown"),
                    base_token=attrs.get("base_token_symbol", ""),
                    quote_token=attrs.get("quote_token_symbol", ""),
                    price_usd=float(attrs.get("base_token_price_usd", 0) or 0),
                    price_change_24h=float(attrs.get("price_change_percentage", {}).get("h24", 0) or 0),
                    volume_24h=float(attrs.get("volume_usd", {}).get("h24", 0) or 0),
                    liquidity_usd=float(attrs.get("reserve_in_usd", 0) or 0),
                    fdv_usd=float(attrs.get("fdv_usd", 0) or 0),
                    market_cap_usd=float(attrs.get("market_cap_usd", 0) or 0),
                    transactions_24h=int(attrs.get("transactions", {}).get("h24", 0) or 0),
                    buys_24h=int(attrs.get("transactions", {}).get("h24_buys", 0) or 0),
                    sells_24h=int(attrs.get("transactions", {}).get("h24_sells", 0) or 0)
                ))
            except Exception as e:
                self.logger.debug(f"[GECKO] Error parsing pool: {e}")
                continue
                
        return pools
        
    # ==================== TRENDING POOLS ====================
    
    async def get_trending_pools(self, network: str = "eth", limit: int = 20) -> List[Pool]:
        """
        Get trending pools on a network (by volume/activity)
        
        Args:
            network: Network ID
            limit: Number of pools
            
        Returns:
            List of trending Pool objects
        """
        endpoint = f"/networks/{network}/trending_pools"
        data = await self._get(endpoint)
        
        if not data:
            return []
            
        pools = []
        for item in data.get("data", [])[:limit]:
            try:
                attrs = item.get("attributes", {})
                pools.append(Pool(
                    address=attrs.get("address", ""),
                    name=attrs.get("name", "Unknown"),
                    network=network,
                    dex=attrs.get("dex_id", "unknown"),
                    base_token=attrs.get("base_token_symbol", ""),
                    quote_token=attrs.get("quote_token_symbol", ""),
                    price_usd=float(attrs.get("base_token_price_usd", 0) or 0),
                    price_change_24h=float(attrs.get("price_change_percentage", {}).get("h24", 0) or 0),
                    volume_24h=float(attrs.get("volume_usd", {}).get("h24", 0) or 0),
                    liquidity_usd=float(attrs.get("reserve_in_usd", 0) or 0),
                    fdv_usd=float(attrs.get("fdv_usd", 0) or 0),
                    market_cap_usd=float(attrs.get("market_cap_usd", 0) or 0),
                    transactions_24h=int(attrs.get("transactions", {}).get("h24", 0) or 0),
                    buys_24h=int(attrs.get("transactions", {}).get("h24_buys", 0) or 0),
                    sells_24h=int(attrs.get("transactions", {}).get("h24_sells", 0) or 0)
                ))
            except Exception as e:
                self.logger.debug(f"[GECKO] Error parsing pool: {e}")
                continue
                
        return pools
        
    # ==================== TOKEN PRICE ====================
    
    async def get_token_price(self, network: str, token_address: str) -> Optional[float]:
        """
        Get current price for a token
        
        Args:
            network: Network ID
            token_address: Token contract address
            
        Returns:
            Price in USD or None
        """
        endpoint = f"/networks/{network}/tokens/{token_address}"
        data = await self._get(endpoint)
        
        if not data:
            return None
            
        try:
            attrs = data.get("data", {}).get("attributes", {})
            return float(attrs.get("price_usd", 0) or 0)
        except:
            return None
            
    # ==================== SEARCH ====================
    
    async def search_pools(self, query: str, network: str = None) -> List[Pool]:
        """
        Search for pools by token name/symbol
        
        Args:
            query: Search query
            network: Optional network filter
            
        Returns:
            List of matching pools
        """
        endpoint = f"/search/pools?query={query}"
        if network:
            endpoint += f"&network={network}"
            
        data = await self._get(endpoint)
        
        if not data:
            return []
            
        pools = []
        for item in data.get("data", []):
            try:
                attrs = item.get("attributes", {})
                pool_network = item.get("relationships", {}).get("network", {}).get("data", {}).get("id", "unknown")
                pools.append(Pool(
                    address=attrs.get("address", ""),
                    name=attrs.get("name", "Unknown"),
                    network=pool_network,
                    dex=attrs.get("dex_id", "unknown"),
                    base_token=attrs.get("base_token_symbol", ""),
                    quote_token=attrs.get("quote_token_symbol", ""),
                    price_usd=float(attrs.get("base_token_price_usd", 0) or 0),
                    price_change_24h=float(attrs.get("price_change_percentage", {}).get("h24", 0) or 0),
                    volume_24h=float(attrs.get("volume_usd", {}).get("h24", 0) or 0),
                    liquidity_usd=float(attrs.get("reserve_in_usd", 0) or 0),
                    fdv_usd=float(attrs.get("fdv_usd", 0) or 0),
                    market_cap_usd=float(attrs.get("market_cap_usd", 0) or 0)
                ))
            except Exception as e:
                self.logger.debug(f"[GECKO] Error parsing search result: {e}")
                continue
                
        return pools
        
    # ==================== OHLCV ====================
    
    async def get_ohlcv(
        self, 
        network: str, 
        pool_address: str,
        timeframe: str = "hour",
        limit: int = 100
    ) -> List[Dict]:
        """
        Get OHLCV candlestick data for a pool
        
        Args:
            network: Network ID
            pool_address: Pool address
            timeframe: minute, hour, day
            limit: Number of candles
            
        Returns:
            List of OHLCV candles
        """
        endpoint = f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
        data = await self._get(endpoint)
        
        if not data:
            return []
            
        try:
            ohlcv_data = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            candles = []
            for candle in ohlcv_data[:limit]:
                candles.append({
                    "timestamp": candle[0],
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                })
            return candles
        except Exception as e:
            self.logger.error(f"[GECKO] OHLCV parse error: {e}")
            return []
