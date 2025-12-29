"""
Backtester - Test trading strategies on historical data

Simulates trading on real historical listing data to validate
the ML model and strategy before live trading.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from src.trading.data_collector import ListingEvent, RealDataCollector
from src.trading.ml_model import TradingMLModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestTrade:
    """A simulated trade in backtesting"""
    symbol: str
    exchange: str
    entry_price: float
    exit_price: float
    entry_date: datetime
    amount_usd: float
    pnl: float
    pnl_percent: float
    ml_confidence: float
    was_correct: bool


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0
    total_pnl_percent: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0
    sharpe_ratio: float = 0
    trades: List[BacktestTrade] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_percent": round(self.total_pnl_percent, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "win_rate": round(self.win_rate, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 2)
        }


class Backtester:
    """
    Backtesting engine for trading strategies
    
    Tests the ML model predictions against historical data
    to measure real performance.
    """
    
    def __init__(
        self, 
        initial_capital: float = 10000,
        position_size_pct: float = 10,
        stop_loss_pct: float = 15,
        take_profit_pct: float = 30
    ):
        self.logger = logger
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
        self.ml_model = TradingMLModel()
        self.data_collector = RealDataCollector()
        
    async def initialize(self):
        """Initialize backtester components"""
        await self.ml_model.initialize()
        await self.data_collector.initialize()
        self.logger.info("[BACKTEST] Backtester initialized")
        
    async def run_backtest(
        self, 
        listings: Optional[List[ListingEvent]] = None,
        confidence_threshold: float = 0.55
    ) -> BacktestResult:
        """
        Run backtest on historical listing data
        
        Args:
            listings: List of historical listings (uses collected data if None)
            confidence_threshold: Minimum ML confidence to trade
            
        Returns:
            BacktestResult with performance metrics
        """
        if listings is None:
            listings = self.data_collector.listings
        
        if not listings:
            self.logger.warning("[BACKTEST] No listing data available")
            return BacktestResult()
        
        self.logger.info(f"[BACKTEST] Running backtest on {len(listings)} listings...")
        
        result = BacktestResult()
        capital = self.initial_capital
        peak_capital = capital
        
        wins = []
        losses = []
        
        for listing in listings:
            if listing.listing_price is None or listing.max_price_24h is None:
                continue
            
            # Get ML prediction
            prediction = self.ml_model.predict(
                symbol=listing.symbol,
                exchange=listing.exchange,
                volume=listing.volume_24h or 0,
                sentiment=listing.sentiment_score or 0.5,
                market_cap=listing.market_cap or 0
            )
            
            # Skip if confidence too low
            if prediction.confidence < confidence_threshold:
                continue
            
            if not prediction.should_buy:
                continue
            
            # Calculate position size
            position_value = capital * (self.position_size_pct / 100)
            
            # Simulate trade
            entry_price = listing.listing_price
            
            # Determine exit price based on stop loss / take profit
            max_potential = (listing.max_price_24h - entry_price) / entry_price * 100
            
            if max_potential >= self.take_profit_pct:
                # Hit take profit
                exit_price = entry_price * (1 + self.take_profit_pct / 100)
                pnl_percent = self.take_profit_pct
            elif listing.min_price_24h:
                min_drop = (entry_price - listing.min_price_24h) / entry_price * 100
                if min_drop >= self.stop_loss_pct:
                    # Hit stop loss
                    exit_price = entry_price * (1 - self.stop_loss_pct / 100)
                    pnl_percent = -self.stop_loss_pct
                else:
                    # Closed at 24h price
                    exit_price = listing.price_24h or entry_price
                    pnl_percent = (exit_price - entry_price) / entry_price * 100
            else:
                exit_price = listing.price_24h or entry_price
                pnl_percent = (exit_price - entry_price) / entry_price * 100
            
            pnl = position_value * (pnl_percent / 100)
            
            # Update capital
            capital += pnl
            
            # Track drawdown
            if capital > peak_capital:
                peak_capital = capital
            drawdown = (peak_capital - capital) / peak_capital * 100
            if drawdown > result.max_drawdown:
                result.max_drawdown = drawdown
            
            # Record trade
            trade = BacktestTrade(
                symbol=listing.symbol,
                exchange=listing.exchange,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_date=listing.listing_date,
                amount_usd=position_value,
                pnl=pnl,
                pnl_percent=pnl_percent,
                ml_confidence=prediction.confidence,
                was_correct=pnl > 0
            )
            
            result.trades.append(trade)
            result.total_trades += 1
            result.total_pnl += pnl
            
            if pnl > 0:
                result.winning_trades += 1
                wins.append(pnl)
            else:
                result.losing_trades += 1
                losses.append(abs(pnl))
        
        # Calculate final metrics
        if result.total_trades > 0:
            result.total_pnl_percent = (capital - self.initial_capital) / self.initial_capital * 100
            result.win_rate = result.winning_trades / result.total_trades * 100
            
            if wins:
                result.avg_win = sum(wins) / len(wins)
            if losses:
                result.avg_loss = sum(losses) / len(losses)
            
            if result.avg_loss > 0:
                result.profit_factor = result.avg_win / result.avg_loss
        
        # Log results
        self._log_results(result)
        
        return result
    
    def _log_results(self, result: BacktestResult):
        """Log backtest results"""
        self.logger.info("=" * 60)
        self.logger.info("[BACKTEST] BACKTEST RESULTS")
        self.logger.info("=" * 60)
        self.logger.info(f"  Initial Capital:  ${self.initial_capital:,.2f}")
        self.logger.info(f"  Final Capital:    ${self.initial_capital + result.total_pnl:,.2f}")
        self.logger.info(f"  Total P&L:        ${result.total_pnl:+,.2f} ({result.total_pnl_percent:+.2f}%)")
        self.logger.info("-" * 60)
        self.logger.info(f"  Total Trades:     {result.total_trades}")
        self.logger.info(f"  Winning Trades:   {result.winning_trades}")
        self.logger.info(f"  Losing Trades:    {result.losing_trades}")
        self.logger.info(f"  Win Rate:         {result.win_rate:.1f}%")
        self.logger.info("-" * 60)
        self.logger.info(f"  Avg Win:          ${result.avg_win:,.2f}")
        self.logger.info(f"  Avg Loss:         ${result.avg_loss:,.2f}")
        self.logger.info(f"  Profit Factor:    {result.profit_factor:.2f}")
        self.logger.info(f"  Max Drawdown:     {result.max_drawdown:.1f}%")
        self.logger.info("=" * 60)
        
        # Best and worst trades
        if result.trades:
            sorted_trades = sorted(result.trades, key=lambda t: t.pnl_percent, reverse=True)
            
            self.logger.info("  BEST TRADES:")
            for trade in sorted_trades[:3]:
                self.logger.info(
                    f"    {trade.symbol}: {trade.pnl_percent:+.1f}% "
                    f"(${trade.pnl:+.2f})"
                )
            
            self.logger.info("  WORST TRADES:")
            for trade in sorted_trades[-3:]:
                self.logger.info(
                    f"    {trade.symbol}: {trade.pnl_percent:+.1f}% "
                    f"(${trade.pnl:+.2f})"
                )


async def run_full_backtest():
    """
    Run a complete backtest cycle:
    1. Collect historical data
    2. Train ML model
    3. Run backtest
    4. Report results
    """
    logger.info("=" * 60)
    logger.info("[BACKTEST] STARTING FULL BACKTEST CYCLE")
    logger.info("=" * 60)
    
    # Initialize components
    data_collector = RealDataCollector()
    await data_collector.initialize()
    
    # Collect data
    listings = await data_collector.collect_all_data()
    data_collector.print_statistics()
    
    if not listings:
        logger.error("[BACKTEST] No data collected, cannot run backtest")
        return None
    
    # Train ML model
    ml_model = TradingMLModel()
    await ml_model.initialize()
    
    training_data = data_collector.get_training_data()
    await ml_model.train(training_data)
    
    # Run backtest
    backtester = Backtester()
    backtester.ml_model = ml_model
    backtester.data_collector = data_collector
    
    result = await backtester.run_backtest(listings)
    
    return result

