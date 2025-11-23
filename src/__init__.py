"""
Cryptobot Ultimate - Main Package
High-Risk / High-Reward Crypto Trading Bot

Multi-strategy automated trading system combining:
- Sniper Bot (DEX new tokens)
- News Trader (announcements)
- AI Sentiment Analysis
- ML Predictive Models
- HFT Arbitrage
- DeFi Yield Optimization
- Copy Trading

Version: 0.1.0
License: MIT
"""

__version__ = "0.1.0"
__author__ = "Cryptobot Team"
__license__ = "MIT"

# Package-level imports for convenience
from src.core.orchestrator import Orchestrator
from src.core.config import Settings

__all__ = ["Orchestrator", "Settings", "__version__"]

