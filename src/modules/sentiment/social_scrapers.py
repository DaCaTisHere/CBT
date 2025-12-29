"""
Social Media Scrapers for Sentiment Analysis

Scrapes and monitors:
- Twitter/X for crypto discussions
- Reddit (r/cryptocurrency, r/bitcoin, etc.)
- Telegram public channels
"""

import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import re

from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


class SocialScraper:
    """Base class for social media scrapers"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logger
        self.is_running = False
        self.posts_collected = 0
    
    async def start(self):
        """Start scraping"""
        raise NotImplementedError
    
    async def stop(self):
        """Stop scraping"""
        self.is_running = False


class TwitterScraper(SocialScraper):
    """
    Twitter scraper for crypto sentiment
    
    Monitors:
    - Trending crypto topics
    - Influencer tweets
    - Community sentiment
    """
    
    # Crypto influencers to monitor
    CRYPTO_INFLUENCERS = [
        "VitalikButerin",
        "cz_binance",
        "elonmusk",
        "APompliano",
        "DocumentingBTC",
        "whale_alert",
        "santimentfeed",
        "glassnode",
    ]
    
    # Keywords to track
    CRYPTO_KEYWORDS = [
        "bitcoin", "btc",
        "ethereum", "eth",
        "crypto", "cryptocurrency",
        "defi", "nft",
        "altcoin", "altseason",
        "bullish", "bearish",
        "moon", "dump", "pump"
    ]
    
    def __init__(self):
        super().__init__("Twitter")
        self.bearer_token = settings.TWITTER_BEARER_TOKEN
        self.session: Optional[aiohttp.ClientSession] = None
        self.seen_tweets = set()
    
    async def start(self):
        """Start Twitter scraping"""
        if not self.bearer_token:
            self.logger.warning(f"[{self.name}] No bearer token, skipping")
            return
        
        self.is_running = True
        self.logger.info(f"[{self.name}] Starting scraper...")
        
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.bearer_token}"}
        )
        
        while self.is_running:
            try:
                # Scrape influencer tweets
                for influencer in self.CRYPTO_INFLUENCERS:
                    tweets = await self._fetch_user_tweets(influencer)
                    
                    for tweet in tweets:
                        if tweet['id'] not in self.seen_tweets:
                            yield await self._process_tweet(tweet, influencer)
                            self.seen_tweets.add(tweet['id'])
                
                # Search for keyword tweets
                for keyword in self.CRYPTO_KEYWORDS[:3]:  # Limit to avoid rate limits
                    tweets = await self._search_tweets(keyword)
                    
                    for tweet in tweets[:5]:  # Top 5 per keyword
                        if tweet['id'] not in self.seen_tweets:
                            yield await self._process_tweet(tweet, f"search:{keyword}")
                            self.seen_tweets.add(tweet['id'])
                
                # Sleep to respect rate limits
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"[{self.name}] Error: {e}")
                await asyncio.sleep(120)
        
        await self.session.close()
    
    async def _fetch_user_tweets(self, username: str) -> List[Dict[str, Any]]:
        """Fetch recent tweets from a user"""
        try:
            # Get user ID
            user_url = f"https://api.twitter.com/2/users/by/username/{username}"
            async with self.session.get(user_url) as response:
                if response.status != 200:
                    return []
                user_data = await response.json()
                user_id = user_data.get('data', {}).get('id')
            
            if not user_id:
                return []
            
            # Get tweets
            tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
            params = {
                "max_results": 10,
                "tweet.fields": "created_at,public_metrics,text"
            }
            
            async with self.session.get(tweets_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [])
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Fetch user tweets failed: {e}")
            return []
    
    async def _search_tweets(self, query: str) -> List[Dict[str, Any]]:
        """Search tweets by keyword"""
        try:
            search_url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                "query": f"{query} -is:retweet lang:en",
                "max_results": 10,
                "tweet.fields": "created_at,public_metrics,text"
            }
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [])
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Search tweets failed: {e}")
            return []
    
    async def _process_tweet(self, tweet: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Process and structure tweet data"""
        self.posts_collected += 1
        
        return {
            "platform": "twitter",
            "source": source,
            "id": tweet.get('id'),
            "text": tweet.get('text', ''),
            "created_at": tweet.get('created_at'),
            "metrics": tweet.get('public_metrics', {}),
            "timestamp": datetime.utcnow()
        }


class RedditScraper(SocialScraper):
    """
    Reddit scraper for crypto sentiment
    
    Monitors:
    - r/cryptocurrency
    - r/bitcoin
    - r/ethtrader
    - r/CryptoMarkets
    """
    
    SUBREDDITS = [
        "cryptocurrency",
        "bitcoin",
        "ethtrader",
        "CryptoMarkets",
        "altcoin",
        "defi"
    ]
    
    def __init__(self):
        super().__init__("Reddit")
        self.session: Optional[aiohttp.ClientSession] = None
        self.seen_posts = set()
    
    async def start(self):
        """Start Reddit scraping"""
        self.is_running = True
        self.logger.info(f"[{self.name}] Starting scraper...")
        
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "CryptoBot/1.0"}
        )
        
        while self.is_running:
            try:
                for subreddit in self.SUBREDDITS:
                    # Fetch hot posts
                    posts = await self._fetch_posts(subreddit, "hot")
                    
                    for post in posts:
                        if post['id'] not in self.seen_posts:
                            yield await self._process_post(post, subreddit)
                            self.seen_posts.add(post['id'])
                
                # Sleep between cycles
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"[{self.name}] Error: {e}")
                await asyncio.sleep(600)
        
        await self.session.close()
    
    async def _fetch_posts(self, subreddit: str, sort: str = "hot") -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
            params = {"limit": 25}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    children = data.get('data', {}).get('children', [])
                    return [child['data'] for child in children]
                return []
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Fetch posts failed: {e}")
            return []
    
    async def _process_post(self, post: Dict[str, Any], subreddit: str) -> Dict[str, Any]:
        """Process and structure Reddit post"""
        self.posts_collected += 1
        
        # Combine title and selftext
        text = post.get('title', '')
        if post.get('selftext'):
            text += " " + post['selftext']
        
        return {
            "platform": "reddit",
            "source": f"r/{subreddit}",
            "id": post.get('id'),
            "text": text,
            "title": post.get('title', ''),
            "score": post.get('score', 0),
            "num_comments": post.get('num_comments', 0),
            "created_utc": post.get('created_utc'),
            "timestamp": datetime.utcnow()
        }


class TelegramScraper(SocialScraper):
    """
    Telegram scraper for crypto channels
    
    Note: Requires Telethon library and API credentials
    """
    
    # Popular crypto channels
    CRYPTO_CHANNELS = [
        "binance_announcements",
        "whale_alert",
        "cryptonews",
    ]
    
    def __init__(self):
        super().__init__("Telegram")
        self.api_id = settings.TELEGRAM_API_ID
        self.api_hash = settings.TELEGRAM_API_HASH
        
        # Telethon client (optional dependency)
        self.client = None
    
    async def start(self):
        """Start Telegram scraping"""
        if not self.api_id or not self.api_hash:
            self.logger.warning(f"[{self.name}] No API credentials, skipping")
            return
        
        try:
            # Try to import Telethon (optional dependency)
            from telethon import TelegramClient
            from telethon.tl.types import Message
            
            self.is_running = True
            self.logger.info(f"[{self.name}] Starting scraper...")
            
            # Initialize client
            self.client = TelegramClient('cryptobot_session', self.api_id, self.api_hash)
            await self.client.start()
            
            # Monitor channels
            while self.is_running:
                try:
                    for channel in self.CRYPTO_CHANNELS:
                        messages = await self._fetch_messages(channel)
                        
                        for message in messages:
                            yield await self._process_message(message, channel)
                    
                    await asyncio.sleep(120)  # Check every 2 minutes
                    
                except Exception as e:
                    self.logger.error(f"[{self.name}] Channel error: {e}")
                    await asyncio.sleep(300)
            
            await self.client.disconnect()
            
        except ImportError:
            self.logger.warning(f"[{self.name}] Telethon not installed, skipping")
        except Exception as e:
            self.logger.error(f"[{self.name}] Error: {e}")
    
    async def _fetch_messages(self, channel: str, limit: int = 10) -> List:
        """Fetch recent messages from channel"""
        try:
            if self.client:
                messages = await self.client.get_messages(channel, limit=limit)
                return messages
            return []
        except Exception as e:
            self.logger.error(f"[{self.name}] Fetch messages failed: {e}")
            return []
    
    async def _process_message(self, message, channel: str) -> Dict[str, Any]:
        """Process Telegram message"""
        self.posts_collected += 1
        
        return {
            "platform": "telegram",
            "source": channel,
            "id": message.id,
            "text": message.text or "",
            "date": message.date,
            "timestamp": datetime.utcnow()
        }


class SocialAggregator:
    """
    Aggregates social media data from all scrapers
    """
    
    def __init__(self):
        self.logger = logger
        self.scrapers: List[SocialScraper] = []
        self.post_callbacks = []
        self.is_running = False
    
    def add_scraper(self, scraper: SocialScraper):
        """Add a scraper"""
        self.scrapers.append(scraper)
        self.logger.info(f"[AGGREGATOR] Added scraper: {scraper.name}")
    
    def on_post(self, callback):
        """Register callback for new posts"""
        self.post_callbacks.append(callback)
    
    async def start(self):
        """Start all scrapers"""
        self.is_running = True
        self.logger.info(f"[AGGREGATOR] Starting {len(self.scrapers)} scrapers...")
        
        # Start all scrapers
        tasks = []
        for scraper in self.scrapers:
            task = asyncio.create_task(self._run_scraper(scraper))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_scraper(self, scraper: SocialScraper):
        """Run a scraper and process its posts"""
        try:
            async for post in scraper.start():
                if post:
                    # Call all callbacks
                    for callback in self.post_callbacks:
                        try:
                            await callback(post)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
        except Exception as e:
            self.logger.error(f"Scraper {scraper.name} error: {e}")
    
    async def stop(self):
        """Stop all scrapers"""
        self.is_running = False
        
        for scraper in self.scrapers:
            await scraper.stop()
        
        self.logger.info(f"[AGGREGATOR] Stopped all scrapers")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from all scrapers"""
        return {
            scraper.name: {
                "posts_collected": scraper.posts_collected,
                "is_running": scraper.is_running
            }
            for scraper in self.scrapers
        }

