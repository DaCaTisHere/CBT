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
    
    # Rate limiting - conservative to avoid Railway shared IP issues
    RATE_LIMIT_CALLS = 10  # Conservative internal limit
    RATE_LIMIT_PERIOD = 60  # seconds
    
    def __init__(self):
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        self._call_times: List[datetime] = []
        self._cache: Dict[str, tuple] = {}  # (data, timestamp)
        self._cache_ttl = 60  # seconds - reduced for fresher data
        self._backoff_until: Optional[datetime] = None
        self._consecutive_429s = 0  # Only count 429 errors, not all errors
        
    async def initialize(self):
        """Initialize the client with custom headers to avoid shared IP rate limits"""
        import random
        import string
        # Unique identifier to avoid shared Railway IP rate limit collisions
        bot_id = ''.join(random.choices(string.ascii_lowercase, k=8))
        self.session = aiohttp.ClientSession(
            headers={
                "Accept": "application/json",
                "User-Agent": f"CryptobotUltimate/{bot_id} (Python/aiohttp)",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=aiohttp.ClientTimeout(total=15)
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
        """Make GET request with rate limiting, caching, and smart backoff"""
        # Check cache first
        cached = self._get_cache(endpoint)
        if cached:
            return cached
        
        # Check if we're in backoff period
        if self._backoff_until and datetime.utcnow() < self._backoff_until:
            remaining = (self._backoff_until - datetime.utcnow()).total_seconds()
            if remaining > 0:
                return None
            else:
                # Backoff expired, reset
                self._backoff_until = None
            
        await self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}{endpoint}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    self._consecutive_429s = 0  # Reset on success
                    self._backoff_until = None
                    data = await response.json()
                    self._set_cache(endpoint, data)
                    return data
                elif response.status == 429:
                    # Smart backoff: 20s first, then 40s, max 90s
                    self._consecutive_429s += 1
                    backoff_time = min(20 * (2 ** (self._consecutive_429s - 1)), 90)
                    self._backoff_until = datetime.utcnow() + timedelta(seconds=backoff_time)
                    self.logger.warning(f"[GECKO] Rate limited - backing off {backoff_time}s (429 #{self._consecutive_429s})")
                    return None
                elif response.status == 404:
                    # Don't count 404 as error (wrong network ID etc)
                    self.logger.debug(f"[GECKO] 404 for {endpoint}")
                    return None
                else:
                    self.logger.warning(f"[GECKO] API error: {response.status} for {endpoint}")
                    return None
        except asyncio.TimeoutError:
            self.logger.debug(f"[GECKO] Timeout for {endpoint}")
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
                
                # Extract BASE TOKEN address from relationships (not the pool LP address)
                base_token_id = (item.get("relationships", {})
                                 .get("base_token", {})
                                 .get("data", {})
                                 .get("id", ""))
                if "_" in base_token_id:
                    token_address = base_token_id.split("_", 1)[1]
                else:
                    token_address = attrs.get("address", "")
                
                pools.append(Pool(
                    address=token_address,
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
                
                # Extract BASE TOKEN address from relationships (not the pool LP address)
                base_token_id = (item.get("relationships", {})
                                 .get("base_token", {})
                                 .get("data", {})
                                 .get("id", ""))
                if "_" in base_token_id:
                    token_address = base_token_id.split("_", 1)[1]
                else:
                    token_address = attrs.get("address", "")
                
                pools.append(Pool(
                    address=token_address,
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
        except Exception:
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
