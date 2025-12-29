"""
Additional Market Data Sources - CoinGecko, LunarCrush

Provides:
- CoinGecko: Trending coins, new listings, market data
- LunarCrush: Social sentiment, galaxy scores
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.utils.logger import get_logger
from src.core.config import settings

logger = get_logger(__name__)


@dataclass
class TrendingCoin:
    """A trending coin from CoinGecko"""
    symbol: str
    name: str
    market_cap_rank: int
    price_btc: float
    score: int  # Trending score (0-100)
    source: str = "coingecko"


@dataclass
class SocialSignal:
    """Social sentiment signal from LunarCrush"""
    symbol: str
    galaxy_score: float  # 0-100
    alt_rank: int
    social_volume: int
    social_score: float
    sentiment: str  # bullish, bearish, neutral
    source: str = "lunarcrush"


class CoinGeckoClient:
    """
    CoinGecko API client
    
    Features:
    - Trending coins
    - New listings
    - Market data
    """
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_ttl = 60  # Cache for 60 seconds
        self.last_fetch: Dict[str, datetime] = {}
        
    async def initialize(self):
        """Initialize the client"""
        self.session = aiohttp.ClientSession()
        self.logger.info("[COINGECKO] Client initialized")
    
    async def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make GET request with caching"""
        cache_key = f"{endpoint}:{str(params)}"
        
        # Check cache
        if cache_key in self.cache:
            if datetime.utcnow() - self.last_fetch.get(cache_key, datetime.min) < timedelta(seconds=self.cache_ttl):
                return self.cache[cache_key]
        
        try:
            url = f"{self.BASE_URL}{endpoint}"
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    self.cache[cache_key] = data
                    self.last_fetch[cache_key] = datetime.utcnow()
                    return data
                elif response.status == 429:
                    self.logger.warning("[COINGECKO] Rate limited, waiting...")
                    await asyncio.sleep(60)
                    return None
                else:
                    self.logger.error(f"[COINGECKO] Error {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"[COINGECKO] Request error: {e}")
            return None
    
    async def get_trending_coins(self) -> List[TrendingCoin]:
        """Get trending coins on CoinGecko"""
        data = await self._get("/search/trending")
        
        if not data:
            return []
        
        trending = []
        for i, coin in enumerate(data.get("coins", [])[:15]):
            item = coin.get("item", {})
            trending.append(TrendingCoin(
                symbol=item.get("symbol", "").upper(),
                name=item.get("name", ""),
                market_cap_rank=item.get("market_cap_rank", 0) or 9999,
                price_btc=item.get("price_btc", 0),
                score=100 - (i * 6)  # Top = 100, decreasing
            ))
        
        self.logger.info(f"[COINGECKO] Found {len(trending)} trending coins")
        return trending
    
    async def get_new_coins(self) -> List[Dict[str, Any]]:
        """Get recently added coins"""
        # Get coins sorted by newest
        data = await self._get("/coins/list", {"include_platform": "false"})
        
        if not data:
            return []
        
        # CoinGecko doesn't provide listing date in this endpoint
        # We'll use the coins/markets endpoint with order=id_desc
        markets = await self._get("/coins/markets", {
            "vs_currency": "usd",
            "order": "id_desc",
            "per_page": 50,
            "page": 1
        })
        
        if not markets:
            return []
        
        new_coins = []
        for coin in markets[:20]:
            new_coins.append({
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "current_price": coin.get("current_price", 0),
                "market_cap": coin.get("market_cap", 0),
                "volume_24h": coin.get("total_volume", 0),
                "price_change_24h": coin.get("price_change_percentage_24h", 0)
            })
        
        return new_coins
    
    async def get_gainers(self) -> List[Dict[str, Any]]:
        """Get top gainers (24h)"""
        data = await self._get("/coins/markets", {
            "vs_currency": "usd",
            "order": "price_change_percentage_24h_desc",
            "per_page": 50,
            "page": 1
        })
        
        if not data:
            return []
        
        gainers = []
        for coin in data:
            change = coin.get("price_change_percentage_24h", 0)
            if change and change > 5:  # Only +5% or more
                gainers.append({
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name", ""),
                    "price": coin.get("current_price", 0),
                    "change_24h": change,
                    "volume": coin.get("total_volume", 0),
                    "market_cap": coin.get("market_cap", 0)
                })
        
        self.logger.info(f"[COINGECKO] Found {len(gainers)} gainers (+5%+)")
        return gainers[:20]
    
    async def close(self):
        """Close the client"""
        if self.session:
            await self.session.close()


class LunarCrushClient:
    """
    LunarCrush API client
    
    Features:
    - Galaxy scores (social + market)
    - Social volume
    - Sentiment analysis
    """
    
    BASE_URL = "https://lunarcrush.com/api4/public"
    
    def __init__(self, api_key: str = None):
        self.logger = logger
        self.api_key = api_key or getattr(settings, 'LUNARCRUSH_API_KEY', None)
        self.session: Optional[aiohttp.ClientSession] = None
        # DISABLED: LunarCrush API returns 404 errors - API seems deprecated
        self.is_enabled = False  # Désactivé car API cassée
        
    async def initialize(self):
        """Initialize the client"""
        if not self.is_enabled:
            self.logger.info("[LUNARCRUSH] Disabled (API deprecated/broken)")
            return
        
        self.session = aiohttp.ClientSession()
        self.logger.info("[LUNARCRUSH] Client initialized")
    
    async def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make GET request"""
        if not self.is_enabled:
            return None
        
        try:
            url = f"{self.BASE_URL}{endpoint}"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.logger.error(f"[LUNARCRUSH] Error {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"[LUNARCRUSH] Request error: {e}")
            return None
    
    async def get_top_social(self, limit: int = 20) -> List[SocialSignal]:
        """Get coins with highest social activity"""
        data = await self._get("/coins/list", {"sort": "social_volume", "limit": limit})
        
        if not data:
            return []
        
        signals = []
        for coin in data.get("data", []):
            galaxy = coin.get("galaxy_score", 0)
            signals.append(SocialSignal(
                symbol=coin.get("symbol", "").upper(),
                galaxy_score=galaxy,
                alt_rank=coin.get("alt_rank", 9999),
                social_volume=coin.get("social_volume", 0),
                social_score=coin.get("social_score", 0),
                sentiment="bullish" if galaxy > 60 else ("bearish" if galaxy < 40 else "neutral")
            ))
        
        self.logger.info(f"[LUNARCRUSH] Found {len(signals)} social signals")
        return signals
    
    async def get_trending(self) -> List[SocialSignal]:
        """Get trending coins by social metrics"""
        data = await self._get("/coins/list", {"sort": "alt_rank", "limit": 30})
        
        if not data:
            return []
        
        signals = []
        for coin in data.get("data", []):
            galaxy = coin.get("galaxy_score", 0)
            if galaxy > 50:  # Only high galaxy scores
                signals.append(SocialSignal(
                    symbol=coin.get("symbol", "").upper(),
                    galaxy_score=galaxy,
                    alt_rank=coin.get("alt_rank", 9999),
                    social_volume=coin.get("social_volume", 0),
                    social_score=coin.get("social_score", 0),
                    sentiment="bullish" if galaxy > 60 else "neutral"
                ))
        
        return signals[:15]
    
    async def close(self):
        """Close the client"""
        if self.session:
            await self.session.close()


class MarketDataAggregator:
    """
    Aggregates data from multiple sources
    
    Combines:
    - CoinGecko trending + gainers
    - LunarCrush social signals
    - Generates trading opportunities
    """
    
    def __init__(self):
        self.logger = logger
        self.coingecko = CoinGeckoClient()
        self.lunarcrush = LunarCrushClient()
        self.is_running = False
        
        # Callbacks
        self.opportunity_callbacks = []
    
    def on_opportunity(self, callback):
        """Register callback for opportunities"""
        self.opportunity_callbacks.append(callback)
    
    async def initialize(self):
        """Initialize all sources"""
        await self.coingecko.initialize()
        await self.lunarcrush.initialize()
        self.logger.info("[AGGREGATOR] Market data aggregator initialized")
    
    async def start(self):
        """Start monitoring sources"""
        self.is_running = True
        
        while self.is_running:
            try:
                await self._scan_opportunities()
                await asyncio.sleep(300)  # Scan every 5 minutes
            except Exception as e:
                self.logger.error(f"[AGGREGATOR] Error: {e}")
                await asyncio.sleep(60)
    
    async def _scan_opportunities(self):
        """Scan all sources for opportunities"""
        opportunities = []
        
        # Get CoinGecko trending
        try:
            trending = await self.coingecko.get_trending_coins()
            for coin in trending[:5]:
                opportunities.append({
                    "symbol": f"{coin.symbol}USDT",
                    "source": "coingecko_trending",
                    "score": coin.score,
                    "reason": f"Trending #{16 - coin.score // 6} on CoinGecko"
                })
        except Exception as e:
            self.logger.error(f"[AGGREGATOR] CoinGecko trending error: {e}")
        
        # Get CoinGecko gainers
        try:
            gainers = await self.coingecko.get_gainers()
            for coin in gainers[:5]:
                opportunities.append({
                    "symbol": f"{coin['symbol']}USDT",
                    "source": "coingecko_gainer",
                    "score": min(100, coin['change_24h'] * 3),
                    "reason": f"Top gainer +{coin['change_24h']:.1f}%",
                    "price": coin['price'],
                    "volume": coin['volume']
                })
        except Exception as e:
            self.logger.error(f"[AGGREGATOR] CoinGecko gainers error: {e}")
        
        # Get LunarCrush social
        try:
            social = await self.lunarcrush.get_top_social()
            for signal in social[:5]:
                if signal.galaxy_score > 60:
                    opportunities.append({
                        "symbol": f"{signal.symbol}USDT",
                        "source": "lunarcrush_social",
                        "score": signal.galaxy_score,
                        "reason": f"High social activity (Galaxy: {signal.galaxy_score:.0f})"
                    })
        except Exception as e:
            self.logger.error(f"[AGGREGATOR] LunarCrush error: {e}")
        
        # Emit opportunities
        for opp in opportunities:
            self.logger.info(f"[AGGREGATOR] Opportunity: {opp['symbol']} - {opp['reason']}")
            for callback in self.opportunity_callbacks:
                try:
                    await callback(opp)
                except Exception as e:
                    self.logger.error(f"[AGGREGATOR] Callback error: {e}")
    
    async def stop(self):
        """Stop the aggregator"""
        self.is_running = False
        await self.coingecko.close()
        await self.lunarcrush.close()


# Global instance
_aggregator: Optional[MarketDataAggregator] = None


def get_market_aggregator() -> MarketDataAggregator:
    """Get global aggregator instance"""
    global _aggregator
    if _aggregator is None:
        _aggregator = MarketDataAggregator()
    return _aggregator


async def start_market_aggregator() -> MarketDataAggregator:
    """Start the market data aggregator"""
    agg = get_market_aggregator()
    await agg.initialize()
    asyncio.create_task(agg.start())
    return agg

