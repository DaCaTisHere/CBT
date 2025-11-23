"""
Sniper Bot Module - Buy new tokens at DEX launch

Strategy: Detect new token listings on DEX (Uniswap, PancakeSwap) and buy instantly
Potential: x10-x100 per successful trade
Risk: Very high (scams, honeypots, rug pulls)
"""

from src.modules.sniper.sniper_bot import SniperBot

__all__ = ["SniperBot"]

