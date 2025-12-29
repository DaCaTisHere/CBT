"""Trading module for Cryptobot Ultimate

Real training system components:
- data_collector: Collects real historical listing data
- ml_model: Machine learning model for predictions
- backtester: Tests strategies on historical data
- real_trainer: Orchestrates the real training process
- paper_trader: Simulated trading with virtual capital
"""

from src.trading.paper_trader import (
    PaperTrader, 
    Portfolio, 
    Position, 
    Trade,
    ListingTrade,
    TradeReason,
    get_paper_trader
)

__all__ = [
    "PaperTrader", 
    "Portfolio", 
    "Position", 
    "Trade",
    "ListingTrade",
    "TradeReason",
    "get_paper_trader"
]
