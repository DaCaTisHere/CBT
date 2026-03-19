"""
Cryptobot Ultimate - Main Package
High-Risk / High-Reward Crypto Trading Bot

Multi-strategy automated trading system:
- Grid Trading (ETH/BNB adaptive grids)
- Pool Detection & Sniping (BSC + Base via DexScreener)
- Momentum Trading (TA-based signals on whitelisted pairs)
- AI-powered trade analysis & honeypot detection

Version: 9.3
License: MIT
"""

__version__ = "0.1.0"
__author__ = "Cryptobot Team"
__license__ = "MIT"

# Package-level imports for convenience
from src.core.orchestrator import Orchestrator
from src.core.config import Settings

__all__ = ["Orchestrator", "Settings", "__version__"]

