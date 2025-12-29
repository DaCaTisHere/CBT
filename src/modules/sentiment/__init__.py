"""
Sentiment Analysis Module

Social media sentiment analysis for crypto trading signals.

Components:
- SentimentAnalyzer: Main analyzer
- NLPEngine: Natural language processing
- Social Scrapers: Twitter, Reddit, Telegram
- Sentiment Aggregator: Time-series aggregation
"""

from src.modules.sentiment.sentiment_analyzer import SentimentAnalyzer
from src.modules.sentiment.nlp_engine import NLPEngine, SentimentAggregator
from src.modules.sentiment.social_scrapers import (
    SocialAggregator,
    TwitterScraper,
    RedditScraper,
    TelegramScraper
)

__all__ = [
    "SentimentAnalyzer",
    "NLPEngine",
    "SentimentAggregator",
    "SocialAggregator",
    "TwitterScraper",
    "RedditScraper",
    "TelegramScraper"
]
