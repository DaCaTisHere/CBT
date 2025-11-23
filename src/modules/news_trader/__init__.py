"""
News Trader Module - Trade on exchange listing announcements

Strategy: Monitor Binance, Coinbase, etc. for listing announcements and buy instantly
Potential: +20-100% per announcement
Risk: High (need very low latency, competition with other bots)
"""

from src.modules.news_trader.news_trader import NewsTrader

__all__ = ["NewsTrader"]

