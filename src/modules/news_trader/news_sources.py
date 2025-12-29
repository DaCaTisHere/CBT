"""
News Sources - Scrapers and monitors for exchange announcements

Monitors:
- Binance announcements (API + web scraping)
- Coinbase blog (RSS + API)
- Kraken blog (RSS)
- Twitter/X official accounts
"""

import asyncio
import aiohttp
import feedparser
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import re

from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


class NewsSource:
    """Base class for news sources"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logger
        self.is_running = False
        self.announcements_detected = 0
    
    async def start(self):
        """Start monitoring"""
        raise NotImplementedError
    
    async def stop(self):
        """Stop monitoring"""
        self.is_running = False


class BinanceAnnouncementMonitor(NewsSource):
    """
    Monitor Binance announcements for new listings
    """
    
    # Binance announcement API endpoint
    ANNOUNCEMENT_API = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    
    # Known announcement categories
    CATEGORY_NEW_LISTING = 48  # New Cryptocurrency Listings
    
    def __init__(self):
        super().__init__("Binance")
        self.seen_ids = set()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        """Start monitoring Binance announcements"""
        self.is_running = True
        self.logger.info(f"[{self.name}] Starting announcement monitor...")
        
        self.session = aiohttp.ClientSession()
        
        while self.is_running:
            try:
                announcements = await self._fetch_announcements()
                
                for announcement in announcements:
                    if announcement['id'] not in self.seen_ids:
                        await self._process_announcement(announcement)
                        self.seen_ids.add(announcement['id'])
                
                # Check every 5 seconds
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"[{self.name}] Error: {e}")
                await asyncio.sleep(10)
        
        await self.session.close()
    
    async def _fetch_announcements(self) -> List[Dict[str, Any]]:
        """
        Fetch latest announcements from Binance API
        """
        try:
            self.logger.info("[Binance] 🔍 Fetching latest announcements from API...")
            payload = {
                "type": 1,
                "catalogId": self.CATEGORY_NEW_LISTING,
                "pageNo": 1,
                "pageSize": 10
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json"
            }
            
            async with self.session.post(
                self.ANNOUNCEMENT_API,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('code') == '000000':
                        articles = data.get('data', {}).get('catalogs', [{}])[0].get('articles', [])
                        return articles
                
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Fetch failed: {e}")
            return []
    
    async def _process_announcement(self, announcement: Dict[str, Any]):
        """
        Process a new announcement
        """
        try:
            article_id = announcement.get('id')
            title = announcement.get('title', '')
            release_date = announcement.get('releaseDate')
            
            self.announcements_detected += 1
            
            self.logger.info(f"")
            self.logger.info(f"🔔 [{self.name}] NEW ANNOUNCEMENT #{self.announcements_detected}")
            self.logger.info(f"   Title: {title}")
            self.logger.info(f"   ID: {article_id}")
            
            # Extract token symbols from title
            tokens = self._extract_tokens(title)
            
            if tokens:
                self.logger.info(f"   Tokens: {', '.join(tokens)}")
                
                # Yield announcement for processing
                return {
                    "source": self.name,
                    "type": "listing",
                    "tokens": tokens,
                    "title": title,
                    "url": f"https://www.binance.com/en/support/announcement/{article_id}",
                    "timestamp": datetime.fromtimestamp(release_date / 1000) if release_date else datetime.utcnow()
                }
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Processing failed: {e}")
            return None
    
    def _extract_tokens(self, title: str) -> List[str]:
        """
        Extract token symbols from announcement title
        
        Examples:
        - "Binance Will List XYZ (XYZ)" → ["XYZ"]
        - "Binance Lists ABC, DEF and GHI" → ["ABC", "DEF", "GHI"]
        """
        tokens = []
        
        # Pattern 1: Symbol in parentheses
        matches = re.findall(r'\(([A-Z]{2,10})\)', title)
        tokens.extend(matches)
        
        # Pattern 2: "List" or "Lists" followed by symbols
        if 'list' in title.lower():
            # Find uppercase words of 2-10 letters
            words = re.findall(r'\b[A-Z]{2,10}\b', title)
            # Filter out common words
            common_words = {'BINANCE', 'USD', 'USDT', 'BTC', 'ETH', 'WILL', 'LIST', 'LISTS', 'AND', 'THE'}
            tokens.extend([w for w in words if w not in common_words])
        
        return list(set(tokens))  # Remove duplicates


class CoinbaseAnnouncementMonitor(NewsSource):
    """
    Monitor Coinbase blog for new listing announcements
    """
    
    # Coinbase blog RSS feed
    BLOG_RSS = "https://blog.coinbase.com/feed"
    
    # Alternative: Coinbase Assets endpoint
    ASSETS_API = "https://api.coinbase.com/v2/assets/search"
    
    def __init__(self):
        super().__init__("Coinbase")
        self.seen_entries = set()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        """Start monitoring Coinbase blog"""
        self.is_running = True
        self.logger.info(f"[{self.name}] Starting announcement monitor...")
        
        self.session = aiohttp.ClientSession()
        
        while self.is_running:
            try:
                announcements = await self._fetch_rss()
                
                for entry in announcements:
                    entry_id = entry.get('id', entry.get('link'))
                    
                    if entry_id not in self.seen_entries:
                        await self._process_entry(entry)
                        self.seen_entries.add(entry_id)
                
                # Check every 10 seconds
                await asyncio.sleep(10)
                
            except Exception as e:
                self.logger.error(f"[{self.name}] Error: {e}")
                await asyncio.sleep(15)
        
        await self.session.close()
    
    async def _fetch_rss(self) -> List[Dict[str, Any]]:
        """
        Fetch RSS feed from Coinbase blog
        """
        try:
            async with self.session.get(
                self.BLOG_RSS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    content = await response.text()
                    
                    # Parse RSS feed (synchronous)
                    feed = await asyncio.to_thread(feedparser.parse, content)
                    
                    # Filter for listing-related entries
                    entries = []
                    for entry in feed.entries[:10]:  # Latest 10
                        title = entry.get('title', '').lower()
                        if any(keyword in title for keyword in ['listing', 'launch', 'support', 'available']):
                            entries.append(entry)
                    
                    return entries
                
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] RSS fetch failed: {e}")
            return []
    
    async def _process_entry(self, entry: Dict[str, Any]):
        """
        Process RSS entry
        """
        try:
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', '')
            
            self.announcements_detected += 1
            
            self.logger.info(f"")
            self.logger.info(f"🔔 [{self.name}] NEW ANNOUNCEMENT #{self.announcements_detected}")
            self.logger.info(f"   Title: {title}")
            
            # Extract tokens
            tokens = self._extract_tokens(title)
            
            if tokens:
                self.logger.info(f"   Tokens: {', '.join(tokens)}")
                
                return {
                    "source": self.name,
                    "type": "listing",
                    "tokens": tokens,
                    "title": title,
                    "url": link,
                    "timestamp": datetime.utcnow()
                }
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Processing failed: {e}")
            return None
    
    def _extract_tokens(self, title: str) -> List[str]:
        """Extract token symbols from title"""
        tokens = []
        
        # Pattern 1: Parentheses
        matches = re.findall(r'\(([A-Z]{2,10})\)', title)
        tokens.extend(matches)
        
        # Pattern 2: Quoted symbols
        matches = re.findall(r'"([A-Z]{2,10})"', title)
        tokens.extend(matches)
        
        # Pattern 3: After "Coinbase adds" or similar
        if 'add' in title.lower() or 'support' in title.lower():
            words = re.findall(r'\b[A-Z]{2,10}\b', title)
            common = {'COINBASE', 'USD', 'USDT', 'BTC', 'ETH', 'ADDS', 'ADD', 'SUPPORT'}
            tokens.extend([w for w in words if w not in common])
        
        return list(set(tokens))


class TwitterMonitor(NewsSource):
    """
    Monitor Twitter for official exchange announcements
    
    Note: Requires Twitter API v2 credentials
    """
    
    # Official exchange accounts to monitor
    MONITORED_ACCOUNTS = [
        "binance",
        "coinbase",
        "krakenfx",
        "OKX",
        "Bybit_Official"
    ]
    
    def __init__(self):
        super().__init__("Twitter")
        self.api_key = settings.TWITTER_API_KEY
        self.api_secret = settings.TWITTER_API_SECRET
        self.bearer_token = settings.TWITTER_BEARER_TOKEN
        
        self.seen_tweets = set()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        """Start monitoring Twitter"""
        if not self.bearer_token:
            self.logger.warning(f"[{self.name}] No bearer token configured, skipping")
            return
        
        self.is_running = True
        self.logger.info(f"[{self.name}] Starting tweet monitor...")
        
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.bearer_token}"}
        )
        
        while self.is_running:
            try:
                for account in self.MONITORED_ACCOUNTS:
                    tweets = await self._fetch_recent_tweets(account)
                    
                    for tweet in tweets:
                        tweet_id = tweet.get('id')
                        
                        if tweet_id not in self.seen_tweets:
                            await self._process_tweet(tweet, account)
                            self.seen_tweets.add(tweet_id)
                
                # Check every 15 seconds
                await asyncio.sleep(15)
                
            except Exception as e:
                self.logger.error(f"[{self.name}] Error: {e}")
                await asyncio.sleep(20)
        
        await self.session.close()
    
    async def _fetch_recent_tweets(self, username: str) -> List[Dict[str, Any]]:
        """
        Fetch recent tweets from a user
        
        Uses Twitter API v2
        """
        try:
            # First, get user ID
            user_url = f"https://api.twitter.com/2/users/by/username/{username}"
            
            async with self.session.get(user_url) as response:
                if response.status != 200:
                    return []
                
                user_data = await response.json()
                user_id = user_data.get('data', {}).get('id')
            
            if not user_id:
                return []
            
            # Get recent tweets
            tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
            params = {
                "max_results": 10,
                "tweet.fields": "created_at,text"
            }
            
            async with self.session.get(tweets_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [])
                
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Tweet fetch failed: {e}")
            return []
    
    async def _process_tweet(self, tweet: Dict[str, Any], account: str):
        """
        Process a tweet
        """
        try:
            tweet_id = tweet.get('id')
            text = tweet.get('text', '')
            created_at = tweet.get('created_at')
            
            # Check if it's a listing announcement
            keywords = ['list', 'listing', 'launch', 'available', 'trading', 'support']
            if not any(kw in text.lower() for kw in keywords):
                return None
            
            self.announcements_detected += 1
            
            self.logger.info(f"")
            self.logger.info(f"🐦 [{self.name}] NEW TWEET from @{account}")
            self.logger.info(f"   {text[:100]}...")
            
            # Extract tokens
            tokens = self._extract_tokens(text)
            
            if tokens:
                self.logger.info(f"   Tokens: {', '.join(tokens)}")
                
                return {
                    "source": f"{self.name}:{account}",
                    "type": "listing",
                    "tokens": tokens,
                    "text": text,
                    "url": f"https://twitter.com/{account}/status/{tweet_id}",
                    "timestamp": datetime.utcnow()
                }
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Tweet processing failed: {e}")
            return None
    
    def _extract_tokens(self, text: str) -> List[str]:
        """Extract token symbols from tweet text"""
        tokens = []
        
        # Pattern 1: $SYMBOL (cashtag)
        matches = re.findall(r'\$([A-Z]{2,10})', text)
        tokens.extend(matches)
        
        # Pattern 2: Parentheses
        matches = re.findall(r'\(([A-Z]{2,10})\)', text)
        tokens.extend(matches)
        
        # Pattern 3: Hashtags
        matches = re.findall(r'#([A-Z]{2,10})', text)
        tokens.extend(matches)
        
        return list(set(tokens))


class NewsAggregator:
    """
    Aggregates news from all sources
    """
    
    def __init__(self):
        self.logger = logger
        self.sources: List[NewsSource] = []
        self.announcement_callbacks = []
        self.is_running = False
    
    def add_source(self, source: NewsSource):
        """Add a news source"""
        self.sources.append(source)
        self.logger.info(f"[AGGREGATOR] Added source: {source.name}")
    
    def on_announcement(self, callback):
        """Register callback for announcements"""
        self.announcement_callbacks.append(callback)
    
    async def start(self):
        """Start all sources"""
        self.is_running = True
        self.logger.info(f"[AGGREGATOR] Starting {len(self.sources)} sources...")
        
        # Start all sources in parallel
        tasks = [source.start() for source in self.sources]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop(self):
        """Stop all sources"""
        self.is_running = False
        
        for source in self.sources:
            await source.stop()
        
        self.logger.info(f"[AGGREGATOR] Stopped all sources")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from all sources"""
        return {
            source.name: {
                "announcements_detected": source.announcements_detected,
                "is_running": source.is_running
            }
            for source in self.sources
        }

