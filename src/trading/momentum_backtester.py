"""
Momentum Backtester - VALIDATE strategies BEFORE deploying

This is the REAL solution:
1. Download historical data from Binance
2. Simulate trades with different strategies
3. Find the strategy that ACTUALLY works
4. Only deploy validated strategies

NO MORE guessing with parameters!
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import json

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class HistoricalCandle:
    """A single candlestick"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    

@dataclass 
class BacktestTrade:
    """A simulated trade"""
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl_percent: float = 0.0
    is_win: bool = False
    strategy_name: str = ""
    # Entry conditions
    rsi_at_entry: float = 50.0
    volume_at_entry: float = 0.0
    change_24h_at_entry: float = 0.0
    distance_from_high: float = 0.0


@dataclass
class StrategyConfig:
    """Configuration for a strategy to test"""
    name: str
    # Entry conditions
    min_change_24h: float = 3.0      # Minimum 24h change to consider
    max_change_24h: float = 20.0     # Maximum 24h change
    max_rsi: float = 60.0            # RSI must be below this
    min_volume_usd: float = 500000   # Minimum volume
    min_pullback: float = 2.0        # Minimum pullback from high
    max_pullback: float = 8.0        # Maximum pullback from high
    # Exit conditions
    stop_loss_pct: float = 3.0       # Stop loss percentage
    take_profit_pct: float = 5.0     # Take profit percentage
    max_hold_hours: int = 24         # Maximum hold time


@dataclass
class BacktestResult:
    """Results from backtesting a strategy"""
    strategy_name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_percent: float = 0.0
    avg_win_percent: float = 0.0
    avg_loss_percent: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    expectancy: float = 0.0  # Expected return per trade
    trades: List[BacktestTrade] = field(default_factory=list)
    
    def calculate_metrics(self):
        """Calculate all metrics from trades"""
        if not self.trades:
            return
            
        self.total_trades = len(self.trades)
        self.winning_trades = sum(1 for t in self.trades if t.is_win)
        self.losing_trades = self.total_trades - self.winning_trades
        
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
            
        wins = [t.pnl_percent for t in self.trades if t.is_win]
        losses = [t.pnl_percent for t in self.trades if not t.is_win]
        
        self.avg_win_percent = sum(wins) / len(wins) if wins else 0
        self.avg_loss_percent = sum(losses) / len(losses) if losses else 0
        self.total_pnl_percent = sum(t.pnl_percent for t in self.trades)
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0.0001
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy (expected return per trade)
        if self.total_trades > 0:
            win_rate_decimal = self.win_rate / 100
            self.expectancy = (win_rate_decimal * self.avg_win_percent) + ((1 - win_rate_decimal) * self.avg_loss_percent)
        
        # Max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for t in self.trades:
            cumulative += t.pnl_percent
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        self.max_drawdown = max_dd


class MomentumBacktester:
    """
    Backtester for momentum strategies
    
    Downloads real historical data and simulates trades to find
    strategies that ACTUALLY work.
    """
    
    # Top liquid pairs to test on
    TEST_SYMBOLS = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
        'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT',
        'LINKUSDT', 'ATOMUSDT', 'LTCUSDT', 'ETCUSDT', 'NEARUSDT',
        'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT'
    ]
    
    def __init__(self):
        self.logger = logger
        self.historical_data: Dict[str, List[HistoricalCandle]] = {}
        self.btc_data: List[HistoricalCandle] = []
        
    async def download_historical_data(self, days: int = 30):
        """Download historical data from Binance"""
        self.logger.info(f"[BACKTEST] Downloading {days} days of data for {len(self.TEST_SYMBOLS)} symbols...")
        
        for symbol in self.TEST_SYMBOLS:
            candles = await self._fetch_klines(symbol, "1h", days * 24)
            if candles:
                self.historical_data[symbol] = candles
                self.logger.info(f"[BACKTEST] {symbol}: {len(candles)} candles loaded")
            await asyncio.sleep(0.1)  # Rate limiting
        
        # Download BTC data for correlation
        self.btc_data = await self._fetch_klines("BTCUSDT", "1h", days * 24)
        
        self.logger.info(f"[BACKTEST] Data download complete. {len(self.historical_data)} symbols ready.")
        
    async def _fetch_klines(self, symbol: str, interval: str, limit: int) -> List[HistoricalCandle]:
        """Fetch klines from Binance"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.binance.com/api/v3/klines"
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": min(limit, 1000)  # Binance max is 1000
                }
                
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        candles = []
                        for k in data:
                            candles.append(HistoricalCandle(
                                timestamp=datetime.fromtimestamp(k[0] / 1000),
                                open=float(k[1]),
                                high=float(k[2]),
                                low=float(k[3]),
                                close=float(k[4]),
                                volume=float(k[5]) * float(k[4])  # Volume in USD
                            ))
                        return candles
        except Exception as e:
            self.logger.error(f"[BACKTEST] Error fetching {symbol}: {e}")
        return []
    
    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50.0
            
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
            
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _is_btc_bullish(self, idx: int) -> bool:
        """Check if BTC is bullish at given index"""
        if not self.btc_data or idx < 24:
            return True
            
        # Check BTC 24h change
        btc_now = self.btc_data[idx].close if idx < len(self.btc_data) else self.btc_data[-1].close
        btc_24h_ago = self.btc_data[idx - 24].close if idx - 24 >= 0 else self.btc_data[0].close
        
        btc_change = ((btc_now - btc_24h_ago) / btc_24h_ago) * 100
        return btc_change > -1.0  # BTC not dumping more than 1%
    
    def run_backtest(self, strategy: StrategyConfig) -> BacktestResult:
        """
        Run backtest for a strategy
        
        Simulates trading on historical data
        """
        result = BacktestResult(strategy_name=strategy.name)
        
        for symbol, candles in self.historical_data.items():
            if len(candles) < 100:
                continue
                
            # Iterate through each hour
            for i in range(50, len(candles) - strategy.max_hold_hours):
                # Check entry conditions
                entry_signal = self._check_entry(candles, i, strategy)
                
                if entry_signal:
                    # Check BTC alignment
                    if not self._is_btc_bullish(i):
                        continue
                    
                    # Simulate the trade
                    trade = self._simulate_trade(symbol, candles, i, strategy)
                    if trade:
                        result.trades.append(trade)
        
        result.calculate_metrics()
        return result
    
    def _check_entry(self, candles: List[HistoricalCandle], idx: int, strategy: StrategyConfig) -> bool:
        """Check if entry conditions are met"""
        if idx < 24:
            return False
            
        current = candles[idx]
        candle_24h_ago = candles[idx - 24]
        
        # Calculate 24h change
        change_24h = ((current.close - candle_24h_ago.close) / candle_24h_ago.close) * 100
        
        # Check change range
        if change_24h < strategy.min_change_24h or change_24h > strategy.max_change_24h:
            return False
        
        # Check volume
        if current.volume < strategy.min_volume_usd:
            return False
        
        # Calculate RSI
        closes = [c.close for c in candles[max(0, idx-50):idx+1]]
        rsi = self._calculate_rsi(closes)
        
        if rsi > strategy.max_rsi:
            return False
        
        # Calculate distance from 24h high
        high_24h = max(c.high for c in candles[idx-24:idx+1])
        distance_from_high = ((high_24h - current.close) / high_24h) * 100
        
        # Check pullback range
        if distance_from_high < strategy.min_pullback or distance_from_high > strategy.max_pullback:
            return False
        
        return True
    
    def _simulate_trade(
        self, 
        symbol: str, 
        candles: List[HistoricalCandle], 
        entry_idx: int,
        strategy: StrategyConfig
    ) -> Optional[BacktestTrade]:
        """Simulate a single trade"""
        entry_candle = candles[entry_idx]
        entry_price = entry_candle.close
        
        # Calculate entry metrics
        closes = [c.close for c in candles[max(0, entry_idx-50):entry_idx+1]]
        rsi = self._calculate_rsi(closes)
        
        candle_24h_ago = candles[entry_idx - 24]
        change_24h = ((entry_price - candle_24h_ago.close) / candle_24h_ago.close) * 100
        
        high_24h = max(c.high for c in candles[entry_idx-24:entry_idx+1])
        distance_from_high = ((high_24h - entry_price) / high_24h) * 100
        
        trade = BacktestTrade(
            symbol=symbol,
            entry_time=entry_candle.timestamp,
            entry_price=entry_price,
            strategy_name=strategy.name,
            rsi_at_entry=rsi,
            volume_at_entry=entry_candle.volume,
            change_24h_at_entry=change_24h,
            distance_from_high=distance_from_high
        )
        
        # Calculate SL/TP prices
        sl_price = entry_price * (1 - strategy.stop_loss_pct / 100)
        tp_price = entry_price * (1 + strategy.take_profit_pct / 100)
        
        # Simulate forward
        for j in range(1, strategy.max_hold_hours + 1):
            if entry_idx + j >= len(candles):
                break
                
            candle = candles[entry_idx + j]
            
            # Check if SL hit (check low)
            if candle.low <= sl_price:
                trade.exit_time = candle.timestamp
                trade.exit_price = sl_price
                trade.exit_reason = "Stop Loss"
                trade.pnl_percent = -strategy.stop_loss_pct
                trade.is_win = False
                return trade
            
            # Check if TP hit (check high)
            if candle.high >= tp_price:
                trade.exit_time = candle.timestamp
                trade.exit_price = tp_price
                trade.exit_reason = "Take Profit"
                trade.pnl_percent = strategy.take_profit_pct
                trade.is_win = True
                return trade
        
        # Timeout - exit at current price
        exit_candle = candles[min(entry_idx + strategy.max_hold_hours, len(candles) - 1)]
        trade.exit_time = exit_candle.timestamp
        trade.exit_price = exit_candle.close
        trade.exit_reason = "Timeout"
        trade.pnl_percent = ((exit_candle.close - entry_price) / entry_price) * 100
        trade.is_win = trade.pnl_percent > 0
        
        return trade
    
    def test_multiple_strategies(self) -> List[BacktestResult]:
        """Test multiple strategy configurations and find the best one"""
        
        strategies = [
            # Strategy 1: Original momentum (baseline)
            StrategyConfig(
                name="Original Momentum",
                min_change_24h=2.0,
                max_change_24h=15.0,
                max_rsi=70,
                min_volume_usd=300000,
                min_pullback=0,  # No pullback requirement
                max_pullback=100,
                stop_loss_pct=3.5,
                take_profit_pct=3.0,
                max_hold_hours=24
            ),
            
            # Strategy 2: Pullback v5.0 (current)
            StrategyConfig(
                name="Pullback v5.0",
                min_change_24h=3.0,
                max_change_24h=20.0,
                max_rsi=60,
                min_volume_usd=500000,
                min_pullback=2.0,
                max_pullback=8.0,
                stop_loss_pct=3.0,
                take_profit_pct=5.0,
                max_hold_hours=24
            ),
            
            # Strategy 3: Ultra Simple RSI
            StrategyConfig(
                name="Simple RSI Oversold",
                min_change_24h=0,
                max_change_24h=100,
                max_rsi=35,  # Only buy when RSI < 35
                min_volume_usd=1000000,
                min_pullback=0,
                max_pullback=100,
                stop_loss_pct=2.0,
                take_profit_pct=3.0,
                max_hold_hours=12
            ),
            
            # Strategy 4: Deep Pullback
            StrategyConfig(
                name="Deep Pullback",
                min_change_24h=5.0,
                max_change_24h=25.0,
                max_rsi=55,
                min_volume_usd=500000,
                min_pullback=4.0,  # Deeper pullback
                max_pullback=10.0,
                stop_loss_pct=2.5,
                take_profit_pct=4.0,
                max_hold_hours=24
            ),
            
            # Strategy 5: Tight SL/TP (Scalp style)
            StrategyConfig(
                name="Tight Scalp",
                min_change_24h=2.0,
                max_change_24h=10.0,
                max_rsi=55,
                min_volume_usd=500000,
                min_pullback=1.5,
                max_pullback=5.0,
                stop_loss_pct=1.5,  # Very tight SL
                take_profit_pct=2.0,  # Small TP
                max_hold_hours=6  # Quick trades
            ),
            
            # Strategy 6: High Volume Only
            StrategyConfig(
                name="High Volume",
                min_change_24h=3.0,
                max_change_24h=15.0,
                max_rsi=60,
                min_volume_usd=2000000,  # Very high volume
                min_pullback=2.0,
                max_pullback=6.0,
                stop_loss_pct=2.5,
                take_profit_pct=4.0,
                max_hold_hours=24
            ),
            
            # Strategy 7: Wide SL/TP (Swing style)
            StrategyConfig(
                name="Swing Trade",
                min_change_24h=5.0,
                max_change_24h=30.0,
                max_rsi=50,  # Even stricter RSI
                min_volume_usd=500000,
                min_pullback=3.0,
                max_pullback=12.0,
                stop_loss_pct=5.0,  # Wider SL
                take_profit_pct=10.0,  # Bigger TP
                max_hold_hours=48  # Longer hold
            ),
            
            # Strategy 8: Mean Reversion
            StrategyConfig(
                name="Mean Reversion",
                min_change_24h=-5.0,  # Buy dips
                max_change_24h=2.0,   # Not pumping
                max_rsi=40,
                min_volume_usd=500000,
                min_pullback=0,
                max_pullback=100,
                stop_loss_pct=3.0,
                take_profit_pct=4.0,
                max_hold_hours=24
            ),
        ]
        
        results = []
        
        for strategy in strategies:
            self.logger.info(f"[BACKTEST] Testing: {strategy.name}")
            result = self.run_backtest(strategy)
            results.append(result)
            
            self.logger.info(
                f"[BACKTEST] {strategy.name}: "
                f"{result.total_trades} trades, "
                f"{result.win_rate:.1f}% win rate, "
                f"{result.total_pnl_percent:.1f}% total PnL, "
                f"Expectancy: {result.expectancy:.2f}%"
            )
        
        # Sort by expectancy (best metric for profitability)
        results.sort(key=lambda x: x.expectancy, reverse=True)
        
        return results
    
    def print_results(self, results: List[BacktestResult]):
        """Print detailed backtest results"""
        print("\n" + "=" * 80)
        print("                    BACKTEST RESULTS - RANKED BY EXPECTANCY")
        print("=" * 80)
        print(f"{'Strategy':<25} {'Trades':>8} {'Win%':>8} {'AvgWin':>8} {'AvgLoss':>8} {'Expect':>8} {'PnL%':>10}")
        print("-" * 80)
        
        for r in results:
            print(
                f"{r.strategy_name:<25} "
                f"{r.total_trades:>8} "
                f"{r.win_rate:>7.1f}% "
                f"{r.avg_win_percent:>7.2f}% "
                f"{r.avg_loss_percent:>7.2f}% "
                f"{r.expectancy:>7.2f}% "
                f"{r.total_pnl_percent:>9.1f}%"
            )
        
        print("=" * 80)
        
        # Best strategy recommendation
        if results and results[0].expectancy > 0:
            best = results[0]
            print(f"\n✅ BEST STRATEGY: {best.strategy_name}")
            print(f"   Expectancy: +{best.expectancy:.2f}% per trade")
            print(f"   Win Rate: {best.win_rate:.1f}%")
            print(f"   Profit Factor: {best.profit_factor:.2f}")
            print(f"   Total PnL: {best.total_pnl_percent:.1f}%")
        else:
            print("\n❌ NO PROFITABLE STRATEGY FOUND")
            print("   All strategies have negative expectancy")
        
        print()


async def run_full_momentum_backtest():
    """Run complete backtest and find the best strategy"""
    backtester = MomentumBacktester()
    
    # Download data
    await backtester.download_historical_data(days=30)
    
    if not backtester.historical_data:
        logger.error("[BACKTEST] No data downloaded, cannot run backtest")
        return None
    
    # Test all strategies
    results = backtester.test_multiple_strategies()
    
    # Print results
    backtester.print_results(results)
    
    return results


# CLI entry point
if __name__ == "__main__":
    asyncio.run(run_full_momentum_backtest())
