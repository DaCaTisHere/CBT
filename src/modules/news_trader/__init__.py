"""
News Trader Module

Automated trading on exchange announcements and listings.

Components:
- NewsTrader: Main trading bot
- NewsAggregator: Aggregates news from multiple sources
- News sources: Binance, Coinbase, Twitter monitors
"""

from src.modules.news_trader.news_trader import NewsTrader
from src.modules.news_trader.news_sources import (
    NewsAggregator,
    BinanceAnnouncementMonitor,
    CoinbaseAnnouncementMonitor,
    TwitterMonitor
)

__all__ = [
    "NewsTrader",
    "NewsAggregator",
    "BinanceAnnouncementMonitor",
    "CoinbaseAnnouncementMonitor",
    "TwitterMonitor"
]
