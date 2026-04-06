"""
AI Sentiment Analyzer - Analyse le sentiment du marché pour un token.

Sources :
1. Twitter/X mentions
2. Reddit discussions
3. Telegram groups
4. Google Trends
5. Fear & Greed Index
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from collections import Counter
import aiohttp

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Analyse le sentiment du marché avec IA."""
    
    # Mots-clés positifs
    BULLISH_KEYWORDS = [
        "moon", "pump", "bullish", "buy", "long", "breakout", "rally",
        "gem", "100x", "1000x", "ath", "new high", "green", "rocket",
        "diamond", "hodl", "hold", "accumulate", "undervalued", "cheap",
        "alpha", "early", "opportunity", "huge", "massive", "explode",
        "lambo", "rich", "profit", "gain", "winner", "golden",
    ]
    
    # Mots-clés négatifs
    BEARISH_KEYWORDS = [
        "dump", "sell", "short", "bearish", "crash", "scam", "rug",
        "rugpull", "honeypot", "avoid", "dead", "rekt", "loss",
        "overvalued", "expensive", "top", "red", "down", "fear",
        "panic", "exit", "warning", "fake", "fraud", "ponzi",
        "bubble", "collapse", "danger", "trap", "manipulation",
    ]
    
    # APIs
    LUNARCRUSH_API = "https://lunarcrush.com/api3"
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 180  # 3 minutes
        self._fear_greed_cache: Optional[Dict[str, Any]] = None
        self._fear_greed_updated: Optional[datetime] = None
        
    async def analyze(
        self, 
        symbol: str,
        token_address: Optional[str] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Analyse le sentiment pour un token.
        
        Returns:
            Tuple[float, Dict]: (sentiment_score -1 to 1, details)
            -1 = très bearish, 0 = neutre, 1 = très bullish
        """
        cache_key = symbol.lower()
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.now() - cached["timestamp"]).total_seconds() < self._cache_ttl:
                return cached["score"], cached["details"]
        
        details = {
            "symbol": symbol,
            "sources": {},
            "keywords_found": {"bullish": [], "bearish": []},
            "overall_sentiment": "neutral",
        }
        
        scores = []
        
        try:
            # Run all sentiment sources in parallel
            results = await asyncio.gather(
                self._get_fear_greed_index(),
                self._get_coingecko_sentiment(symbol),
                self._analyze_social_volume(symbol),
                return_exceptions=True
            )
            
            # Process Fear & Greed Index (market-wide)
            if isinstance(results[0], dict) and not results[0].get("error"):
                fg_data = results[0]
                details["sources"]["fear_greed"] = fg_data
                # Normalize to -1 to 1 (0-100 -> -1 to 1)
                fg_score = (fg_data.get("value", 50) - 50) / 50
                scores.append(("fear_greed", fg_score, 0.2))  # 20% weight
                
            # Process CoinGecko sentiment
            if isinstance(results[1], dict) and not results[1].get("error"):
                cg_data = results[1]
                details["sources"]["coingecko"] = cg_data
                if cg_data.get("sentiment_score") is not None:
                    scores.append(("coingecko", cg_data["sentiment_score"], 0.3))
                    
            # Process social volume analysis
            if isinstance(results[2], dict) and not results[2].get("error"):
                social_data = results[2]
                details["sources"]["social"] = social_data
                if social_data.get("sentiment_score") is not None:
                    scores.append(("social", social_data["sentiment_score"], 0.5))
                details["keywords_found"] = social_data.get("keywords_found", {})
            
            # Calculate weighted average
            if scores:
                total_weight = sum(s[2] for s in scores)
                weighted_score = sum(s[1] * s[2] for s in scores) / total_weight
            else:
                weighted_score = 0.0
            
            # Determine sentiment label
            if weighted_score > 0.3:
                details["overall_sentiment"] = "bullish"
            elif weighted_score > 0.1:
                details["overall_sentiment"] = "slightly_bullish"
            elif weighted_score < -0.3:
                details["overall_sentiment"] = "bearish"
            elif weighted_score < -0.1:
                details["overall_sentiment"] = "slightly_bearish"
            else:
                details["overall_sentiment"] = "neutral"
            
            # Cache result
            self._cache[cache_key] = {
                "score": weighted_score,
                "details": details,
                "timestamp": datetime.now(),
            }
            
            # Log
            emoji = "🟢" if weighted_score > 0.2 else "🔴" if weighted_score < -0.2 else "⚪"
            logger.info(f"{emoji} Sentiment {symbol}: {weighted_score:.2f} ({details['overall_sentiment']})")
            
            return weighted_score, details
            
        except Exception as e:
            logger.error(f"Sentiment analysis error for {symbol}: {e}")
            details["error"] = str(e)
            return 0.0, details
    
    async def _get_fear_greed_index(self) -> Dict[str, Any]:
        """Récupère le Fear & Greed Index crypto."""
        # Use cache if recent
        if self._fear_greed_cache and self._fear_greed_updated:
            if (datetime.now() - self._fear_greed_updated).total_seconds() < 3600:
                return self._fear_greed_cache
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.alternative.me/fng/"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data"):
                            result = {
                                "value": int(data["data"][0]["value"]),
                                "classification": data["data"][0]["value_classification"],
                                "timestamp": datetime.now().isoformat(),
                            }
                            self._fear_greed_cache = result
                            self._fear_greed_updated = datetime.now()
                            return result
                    return {"error": f"API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_coingecko_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Récupère les données de sentiment de CoinGecko."""
        try:
            async with aiohttp.ClientSession() as session:
                # First, search for the coin
                search_url = f"{self.COINGECKO_API}/search?query={symbol}"
                async with session.get(search_url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        coins = data.get("coins", [])
                        
                        if not coins:
                            return {"error": "Coin not found"}
                        
                        coin_id = coins[0]["id"]
                        
                        # Get coin data with community data
                        coin_url = f"{self.COINGECKO_API}/coins/{coin_id}"
                        async with session.get(coin_url, timeout=10) as coin_response:
                            if coin_response.status == 200:
                                coin_data = await coin_response.json()
                                
                                # Extract sentiment data
                                sentiment_up = coin_data.get("sentiment_votes_up_percentage", 50)
                                sentiment_down = coin_data.get("sentiment_votes_down_percentage", 50)
                                
                                # Normalize to -1 to 1
                                if sentiment_up + sentiment_down > 0:
                                    sentiment_score = (sentiment_up - sentiment_down) / 100
                                else:
                                    sentiment_score = 0
                                
                                return {
                                    "sentiment_score": sentiment_score,
                                    "up_votes": sentiment_up,
                                    "down_votes": sentiment_down,
                                    "community_score": coin_data.get("community_score", 0),
                                    "developer_score": coin_data.get("developer_score", 0),
                                    "twitter_followers": coin_data.get("community_data", {}).get("twitter_followers", 0),
                                    "reddit_subscribers": coin_data.get("community_data", {}).get("reddit_subscribers", 0),
                                }
                            return {"error": f"Coin API returned {coin_response.status}"}
                    return {"error": f"Search API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _analyze_social_volume(self, symbol: str) -> Dict[str, Any]:
        """
        Analyse le volume social via CryptoCompare (gratuit, sans clé API).
        Endpoint: /data/v2/news/?categories=<symbol>
        """
        base = symbol.replace("USDT", "").replace("BTC", "").replace("ETH", "").upper()
        bullish_found: List[str] = []
        bearish_found: List[str] = []
        mention_count = 0

        try:
            url = f"https://min-api.cryptocompare.com/data/v2/news/?categories={base}&excludeCategories=Sponsored"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        articles = data.get("Data", [])[:15]  # Take latest 15 articles
                        mention_count = len(articles)

                        # Analyse text of recent articles
                        for article in articles:
                            text = (article.get("title", "") + " " + article.get("body", "")[:200]).lower()
                            for kw in self.BULLISH_KEYWORDS:
                                if kw in text and kw not in bullish_found:
                                    bullish_found.append(kw)
                            for kw in self.BEARISH_KEYWORDS:
                                if kw in text and kw not in bearish_found:
                                    bearish_found.append(kw)

            total_keywords = len(bullish_found) + len(bearish_found)
            if total_keywords > 0:
                sentiment_score = (len(bullish_found) - len(bearish_found)) / total_keywords
            elif mention_count > 5:
                sentiment_score = 0.05  # Many articles = slightly positive attention
            else:
                sentiment_score = 0.0

        except Exception as e:
            logger.debug(f"[SENTIMENT] CryptoCompare news failed for {base}: {e}")
            sentiment_score = 0.0

        return {
            "sentiment_score": round(sentiment_score, 3),
            "keywords_found": {
                "bullish": bullish_found[:8],
                "bearish": bearish_found[:8],
            },
            "mention_count": mention_count,
            "source": "cryptocompare_news",
        }
    
    def analyze_text(self, text: str) -> Tuple[float, Dict[str, Any]]:
        """
        Analyse le sentiment d'un texte.
        
        Returns:
            Tuple[float, Dict]: (score -1 to 1, details)
        """
        text_lower = text.lower()
        
        bullish_found = [kw for kw in self.BULLISH_KEYWORDS if kw in text_lower]
        bearish_found = [kw for kw in self.BEARISH_KEYWORDS if kw in text_lower]
        
        bullish_count = len(bullish_found)
        bearish_count = len(bearish_found)
        total = bullish_count + bearish_count
        
        if total == 0:
            score = 0.0
        else:
            score = (bullish_count - bearish_count) / total
        
        return score, {
            "bullish_keywords": bullish_found,
            "bearish_keywords": bearish_found,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
        }
    
    async def get_trending_tokens(self) -> List[Dict[str, Any]]:
        """Récupère les tokens trending sur les réseaux sociaux."""
        try:
            async with aiohttp.ClientSession() as session:
                # CoinGecko trending
                url = f"{self.COINGECKO_API}/search/trending"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        coins = data.get("coins", [])
                        
                        trending = []
                        for coin_data in coins[:10]:
                            coin = coin_data.get("item", {})
                            trending.append({
                                "symbol": coin.get("symbol"),
                                "name": coin.get("name"),
                                "market_cap_rank": coin.get("market_cap_rank"),
                                "score": coin.get("score"),
                            })
                        return trending
                    return []
        except Exception as e:
            logger.error(f"Error fetching trending: {e}")
            return []


# Singleton
_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get or create sentiment analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer
