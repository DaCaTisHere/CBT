"""
GeckoTerminal Integration Module

Provides access to real-time DEX data across 200+ chains:
- New pool detection for early sniping
- Trending pool tracking for momentum plays
- Real-time price feeds for DEX tokens
"""

from src.modules.geckoterminal.gecko_client import GeckoTerminalClient
from src.modules.geckoterminal.pool_detector import PoolDetector
from src.modules.geckoterminal.trending_tracker import TrendingTracker

__all__ = ['GeckoTerminalClient', 'PoolDetector', 'TrendingTracker']
