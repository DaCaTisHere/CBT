"""
Sentiment Analyzer - Complete Implementation

Analyzes social media sentiment to generate trading signals.

Features:
- Multi-platform scraping (Twitter, Reddit, Telegram)
- NLP sentiment analysis
- Token-specific sentiment tracking
- Trading signal generation
- Real-time sentiment scores
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from src.core.config import settings
from src.core.risk_manager import RiskManager
from src.utils.logger import get_logger

# Sentiment components
from src.modules.sentiment.social_scrapers import (
    SocialAggregator,
    TwitterScraper,
    RedditScraper,
    TelegramScraper
)
from src.modules.sentiment.nlp_engine import NLPEngine, SentimentAggregator


logger = get_logger(__name__)


class SentimentAnalyzer:
    """
    Sentiment analysis bot for crypto trading
    
    Strategy:
    1. Scrape social media for crypto discussions
    2. Analyze sentiment with NLP
    3. Aggregate sentiment by token
    4. Generate trading signals
    5. Track sentiment trends
    """
    
    # Signal thresholds
    STRONG_BULLISH_THRESHOLD = 0.6
    BULLISH_THRESHOLD = 0.3
    BEARISH_THRESHOLD = -0.3
    STRONG_BEARISH_THRESHOLD = -0.6
    
    # Minimum volume for signals
    MIN_VOLUME_FOR_SIGNAL = 20  # Min 20 posts in window
    
    # Time windows for aggregation
    SHORT_WINDOW_MINUTES = 15
    MEDIUM_WINDOW_MINUTES = 60
    LONG_WINDOW_MINUTES = 240  # 4 hours
    
    def __init__(self, risk_manager: RiskManager):
        """
        Initialize sentiment analyzer
        
        Args:
            risk_manager: Risk manager instance
        """
        self.logger = logger
        self.risk_manager = risk_manager
        
        self.is_running = False
        self.is_initialized = False
        
        # Components
        self.social_aggregator = SocialAggregator()
        self.nlp_engine = NLPEngine()
        
        # Sentiment aggregators for different timeframes
        self.sentiment_short = SentimentAggregator(self.SHORT_WINDOW_MINUTES)
        self.sentiment_medium = SentimentAggregator(self.MEDIUM_WINDOW_MINUTES)
        self.sentiment_long = SentimentAggregator(self.LONG_WINDOW_MINUTES)
        
        # Token tracking
        self.token_sentiments: Dict[str, Dict] = {}
        
        # Statistics
        self.posts_processed = 0
        self.signals_generated = 0
        self.signal_callbacks = []
        
        self.logger.info("🧠 Sentiment Analyzer initialized")
    
    async def initialize(self):
        """Initialize sentiment analyzer"""
        try:
            self.logger.info("[INIT] Initializing Sentiment Analyzer...")
            
            # Initialize NLP engine
            await self.nlp_engine.initialize()
            self.logger.info("   ✅ NLP engine initialized")
            
            # Initialize social scrapers
            await self._initialize_scrapers()
            
            # Register callback for social posts
            self.social_aggregator.on_post(self._handle_social_post)
            
            self.is_initialized = True
            self.logger.info("[OK] Sentiment Analyzer initialized")
            
        except Exception as e:
            self.logger.error(f"Sentiment Analyzer initialization failed: {e}")
            raise
    
    async def _initialize_scrapers(self):
        """Initialize and configure social media scrapers"""
        self.logger.info("   Initializing social scrapers...")
        
        # Add Twitter scraper
        if settings.TWITTER_BEARER_TOKEN:
            twitter = TwitterScraper()
            self.social_aggregator.add_scraper(twitter)
            self.logger.info("   ✅ Twitter scraper added")
        
        # Add Reddit scraper (no auth required)
        reddit = RedditScraper()
        self.social_aggregator.add_scraper(reddit)
        self.logger.info("   ✅ Reddit scraper added")
        
        # Add Telegram scraper (optional)
        if hasattr(settings, 'TELEGRAM_API_ID') and settings.TELEGRAM_API_ID:
            telegram = TelegramScraper()
            self.social_aggregator.add_scraper(telegram)
            self.logger.info("   ✅ Telegram scraper added")
        
        total_scrapers = len(self.social_aggregator.scrapers)
        self.logger.info(f"   📡 {total_scrapers} scrapers configured")
    
    def on_signal(self, callback):
        """Register callback for trading signals"""
        self.signal_callbacks.append(callback)
    
    async def run(self):
        """Main sentiment analyzer loop"""
        if not self.is_initialized:
            await self.initialize()
        
        self.is_running = True
        self.logger.info("[RUN]  Sentiment Analyzer started - monitoring social media...")
        
        try:
            # Start social aggregator (scrapes all platforms)
            scraper_task = asyncio.create_task(self.social_aggregator.start())
            
            # Start signal generation loop
            signal_task = asyncio.create_task(self._signal_generation_loop())
            
            # Start sentiment reporting loop
            report_task = asyncio.create_task(self._reporting_loop())
            
            # Wait for tasks
            await asyncio.gather(scraper_task, signal_task, report_task)
            
        except asyncio.CancelledError:
            self.logger.info("Sentiment Analyzer cancelled")
        except Exception as e:
            self.logger.error(f"Sentiment Analyzer error: {e}")
        finally:
            await self.stop()
    
    async def _handle_social_post(self, post: Dict[str, Any]):
        """
        Handle a social media post
        
        Args:
            post: Post data from social scraper
        """
        try:
            self.posts_processed += 1
            
            # Extract text
            text = post.get("text", "")
            if not text or len(text) < 10:
                return
            
            # Analyze sentiment
            sentiment = await self.nlp_engine.analyze_sentiment(text)
            
            # Extract mentioned tokens
            tokens = self.nlp_engine.extract_tokens_mentioned(text)
            
            # Build sentiment data
            sentiment_data = {
                "platform": post.get("platform"),
                "source": post.get("source"),
                "text": text[:200],  # First 200 chars
                "sentiment": sentiment["sentiment"],
                "score": sentiment["score"],
                "confidence": sentiment["confidence"],
                "tokens": tokens,
                "timestamp": post.get("timestamp", datetime.utcnow()),
                "metrics": post.get("metrics", {})
            }
            
            # Add to aggregators
            self.sentiment_short.add_sentiment(sentiment_data)
            self.sentiment_medium.add_sentiment(sentiment_data)
            self.sentiment_long.add_sentiment(sentiment_data)
            
            # Update token-specific sentiment
            for token in tokens:
                await self._update_token_sentiment(token, sentiment_data)
            
            # Log occasionally
            if self.posts_processed % 50 == 0:
                self.logger.info(f"   📊 Processed {self.posts_processed} posts")
            
        except Exception as e:
            self.logger.error(f"Error handling social post: {e}")
    
    async def _update_token_sentiment(self, token: str, sentiment_data: Dict[str, Any]):
        """Update sentiment tracking for a specific token"""
        if token not in self.token_sentiments:
            self.token_sentiments[token] = {
                "token": token,
                "mentions": 0,
                "sentiment_history": [],
                "last_signal": None,
                "last_signal_time": None
            }
        
        # Update mentions
        self.token_sentiments[token]["mentions"] += 1
        
        # Add to history
        self.token_sentiments[token]["sentiment_history"].append({
            "score": sentiment_data["score"],
            "timestamp": sentiment_data["timestamp"]
        })
        
        # Keep only recent history (last 24 hours)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self.token_sentiments[token]["sentiment_history"] = [
            item for item in self.token_sentiments[token]["sentiment_history"]
            if item["timestamp"] > cutoff
        ]
    
    async def _signal_generation_loop(self):
        """Generate trading signals based on sentiment"""
        while self.is_running:
            try:
                # Check sentiment for tracked tokens
                for token, data in list(self.token_sentiments.items()):
                    signal = await self._generate_signal(token)
                    
                    if signal:
                        await self._emit_signal(signal)
                
                # Check every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Signal generation error: {e}")
                await asyncio.sleep(60)
    
    async def _generate_signal(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal for a token
        
        Args:
            token: Token symbol (e.g., "BTC")
        
        Returns:
            Signal dict or None
        """
        try:
            # Get aggregated sentiment for this token
            short_sentiment = self.sentiment_short.get_aggregated_sentiment(token)
            medium_sentiment = self.sentiment_medium.get_aggregated_sentiment(token)
            
            # Check volume threshold
            if short_sentiment["volume"] < self.MIN_VOLUME_FOR_SIGNAL:
                return None
            
            # Check if we recently signaled this token
            token_data = self.token_sentiments.get(token, {})
            last_signal_time = token_data.get("last_signal_time")
            
            if last_signal_time:
                time_since_signal = (datetime.utcnow() - last_signal_time).total_seconds()
                if time_since_signal < 3600:  # 1 hour cooldown
                    return None
            
            # Determine signal strength
            score = short_sentiment["score"]
            confidence = short_sentiment["confidence"]
            
            # Generate signal
            signal = None
            
            if score >= self.STRONG_BULLISH_THRESHOLD and confidence >= 0.7:
                signal = {
                    "token": token,
                    "direction": "BUY",
                    "strength": "STRONG",
                    "score": score,
                    "confidence": confidence,
                    "volume": short_sentiment["volume"],
                    "sentiment": short_sentiment,
                    "reason": f"Strong bullish sentiment (score: {score:.2f})",
                    "timestamp": datetime.utcnow()
                }
            
            elif score >= self.BULLISH_THRESHOLD and confidence >= 0.6:
                signal = {
                    "token": token,
                    "direction": "BUY",
                    "strength": "MODERATE",
                    "score": score,
                    "confidence": confidence,
                    "volume": short_sentiment["volume"],
                    "sentiment": short_sentiment,
                    "reason": f"Bullish sentiment (score: {score:.2f})",
                    "timestamp": datetime.utcnow()
                }
            
            elif score <= self.STRONG_BEARISH_THRESHOLD and confidence >= 0.7:
                signal = {
                    "token": token,
                    "direction": "SELL",
                    "strength": "STRONG",
                    "score": score,
                    "confidence": confidence,
                    "volume": short_sentiment["volume"],
                    "sentiment": short_sentiment,
                    "reason": f"Strong bearish sentiment (score: {score:.2f})",
                    "timestamp": datetime.utcnow()
                }
            
            elif score <= self.BEARISH_THRESHOLD and confidence >= 0.6:
                signal = {
                    "token": token,
                    "direction": "SELL",
                    "strength": "MODERATE",
                    "score": score,
                    "confidence": confidence,
                    "volume": short_sentiment["volume"],
                    "sentiment": short_sentiment,
                    "reason": f"Bearish sentiment (score: {score:.2f})",
                    "timestamp": datetime.utcnow()
                }
            
            # Update last signal
            if signal:
                self.token_sentiments[token]["last_signal"] = signal
                self.token_sentiments[token]["last_signal_time"] = datetime.utcnow()
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Signal generation failed for {token}: {e}")
            return None
    
    async def _emit_signal(self, signal: Dict[str, Any]):
        """Emit a trading signal"""
        self.signals_generated += 1
        
        self.logger.info(f"")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"📊 SENTIMENT SIGNAL #{self.signals_generated}")
        self.logger.info(f"   Token: {signal['token']}")
        self.logger.info(f"   Direction: {signal['direction']} ({signal['strength']})")
        self.logger.info(f"   Score: {signal['score']:.3f}")
        self.logger.info(f"   Confidence: {signal['confidence']:.2%}")
        self.logger.info(f"   Volume: {signal['volume']} posts")
        self.logger.info(f"   Reason: {signal['reason']}")
        self.logger.info(f"{'='*60}")
        
        # Call registered callbacks
        for callback in self.signal_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                self.logger.error(f"Signal callback error: {e}")
    
    async def _reporting_loop(self):
        """Periodic reporting of sentiment stats"""
        while self.is_running:
            try:
                # Report every 15 minutes
                await asyncio.sleep(900)
                
                self.logger.info(f"")
                self.logger.info(f"📊 SENTIMENT REPORT")
                self.logger.info(f"   Posts processed: {self.posts_processed}")
                self.logger.info(f"   Signals generated: {self.signals_generated}")
                self.logger.info(f"   Tokens tracked: {len(self.token_sentiments)}")
                
                # Top 5 tokens by mentions
                sorted_tokens = sorted(
                    self.token_sentiments.items(),
                    key=lambda x: x[1]["mentions"],
                    reverse=True
                )[:5]
                
                if sorted_tokens:
                    self.logger.info(f"   Top tokens:")
                    for token, data in sorted_tokens:
                        mentions = data["mentions"]
                        sentiment = self.sentiment_medium.get_aggregated_sentiment(token)
                        self.logger.info(f"      {token}: {mentions} mentions, sentiment: {sentiment['sentiment']} ({sentiment['score']:.2f})")
                
            except Exception as e:
                self.logger.error(f"Reporting error: {e}")
    
    async def get_sentiment(self, token: str) -> Dict[str, Any]:
        """
        Get current sentiment for a token
        
        Args:
            token: Token symbol
        
        Returns:
            Sentiment data
        """
        return {
            "token": token,
            "short_term": self.sentiment_short.get_aggregated_sentiment(token),
            "medium_term": self.sentiment_medium.get_aggregated_sentiment(token),
            "long_term": self.sentiment_long.get_aggregated_sentiment(token),
            "mentions_24h": self.token_sentiments.get(token, {}).get("mentions", 0)
        }
    
    async def stop(self):
        """Stop sentiment analyzer"""
        self.is_running = False
        
        # Stop social aggregator
        await self.social_aggregator.stop()
        
        self.logger.info("[STOP]  Sentiment Analyzer stopped")
        self.logger.info(f"   Posts processed: {self.posts_processed}")
        self.logger.info(f"   Signals generated: {self.signals_generated}")
        self.logger.info(f"   Tokens tracked: {len(self.token_sentiments)}")
    
    async def is_healthy(self) -> bool:
        """Health check"""
        return self.is_running and self.is_initialized
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get sentiment analyzer statistics"""
        stats = {
            "posts_processed": self.posts_processed,
            "signals_generated": self.signals_generated,
            "tokens_tracked": len(self.token_sentiments),
            "nlp_stats": self.nlp_engine.get_stats(),
            "scraper_stats": self.social_aggregator.get_stats()
        }
        
        return stats
