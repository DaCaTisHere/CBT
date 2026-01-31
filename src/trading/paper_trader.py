"""
Paper Trading System - Simulated Trading for Training

Simulates trades with virtual capital to test strategies without risk.
Includes auto-learning integration for continuous improvement.
"""

import asyncio
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import random

from src.utils.logger import get_logger

# Auto-learning system
try:
    from src.ml.auto_learner import AutoLearner
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    AutoLearner = None

logger = get_logger(__name__)


# Global instance
_paper_trader: Optional["PaperTrader"] = None


class TradeReason(Enum):
    """Reasons for trading"""
    NEW_LISTING = "new_listing"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    MANUAL = "manual"
    SIGNAL = "signal"


def get_paper_trader() -> "PaperTrader":
    """Get or create the global paper trader instance"""
    global _paper_trader
    if _paper_trader is None:
        _paper_trader = PaperTrader()
    return _paper_trader


@dataclass
class Position:
    """A simulated trading position with trailing stop and scaled TP"""
    symbol: str
    entry_price: float
    amount: float
    entry_time: datetime
    side: str = "BUY"  # BUY or SELL
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # SWING TRADE STRATEGY v6.0 - BACKTESTED (94.7% win rate)
    highest_price: Optional[float] = None  # Track highest price seen
    trailing_stop_pct: float = 0.03  # 3% trailing stop (wider for swing trades)
    trailing_activated: bool = False  # Activated after +5% profit
    # Scaled take-profits - SWING TRADE v6.0 (from backtest: TP=10%, SL=5%)
    tp1_hit: bool = False  # +4% - sell 20%
    tp2_hit: bool = False  # +7% - sell 30%
    tp3_hit: bool = False  # +10% - sell remaining (backtest validated)
    original_amount: Optional[float] = None  # Track original amount
    # Timeout for stagnant positions
    last_movement_time: Optional[datetime] = None  # Track last significant price movement
    # Signal features for ML learning
    signal_features: Optional[Dict[str, Any]] = None  # Stores signal data for auto-learning
    
    @property
    def value(self) -> float:
        return self.entry_price * self.amount


@dataclass
class ListingTrade:
    """A new listing trade record"""
    symbol: str
    exchange: str
    entry_price: float
    amount: float
    value_usd: float
    timestamp: datetime


@dataclass
class Trade:
    """Record of a completed trade"""
    id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    amount: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_percent: float
    reason: str  # Why trade was closed


@dataclass 
class Portfolio:
    """Virtual portfolio for paper trading"""
    initial_capital: float = 10000.0
    cash: float = 10000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    trade_history: List[Trade] = field(default_factory=list)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    @property
    def total_value(self) -> float:
        """Total portfolio value (cash + positions)"""
        positions_value = sum(p.value for p in self.positions.values())
        return self.cash + positions_value
    
    @property
    def total_pnl(self) -> float:
        """Total profit/loss"""
        return self.total_value - self.initial_capital
    
    @property
    def total_pnl_percent(self) -> float:
        """Total profit/loss percentage"""
        return (self.total_pnl / self.initial_capital) * 100
    
    @property
    def win_rate(self) -> float:
        """Win rate percentage"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100


class PaperTrader:
    """
    Paper Trading Engine
    
    Simulates trading with virtual capital to test strategies.
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.logger = logger
        self.portfolio = Portfolio(
            initial_capital=initial_capital,
            cash=initial_capital
        )
        self.is_running = False
        self.price_cache: Dict[str, float] = {}
        self.trade_counter = 0
        
        # Trading parameters - OPTIMIZED for quality over quantity
        self.max_position_size = 0.08  # 8% of portfolio per trade
        self.default_stop_loss = 0.03  # 3% stop loss (plus serré, était 4%)
        self.default_take_profit = 0.10  # 10% take profit target
        
        # Auto-learning system
        self.auto_learner: Optional[AutoLearner] = None
        if ML_AVAILABLE:
            self.auto_learner = AutoLearner()
            self.logger.info("[PAPER] 🧠 Auto-learning system enabled")
        
        self.logger.info(f"[PAPER] Paper Trader initialized with ${initial_capital:,.2f}")
    
    async def initialize(self):
        """Initialize paper trader and auto-learning system"""
        self.is_running = True
        
        # Initialize auto-learner
        if self.auto_learner:
            await self.auto_learner.initialize()
            await self.auto_learner.start()
            self.logger.info("[PAPER] 🧠 Auto-learning system started")
        
        self.logger.info("[PAPER] Paper Trader ready for simulated trading")
        
        # Load saved state if exists
        await self._load_state()
    
    async def buy(
        self, 
        symbol: str, 
        price: float, 
        amount: Optional[float] = None,
        reason: str = "Signal",
        stop_loss_pct: Optional[float] = None,
        signal_features: Optional[Dict[str, Any]] = None
    ) -> Optional[Position]:
        """
        Execute a simulated BUY order with dynamic stop-loss
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            price: Entry price
            amount: Amount to buy (default: max_position_size of portfolio)
            reason: Reason for the trade
            stop_loss_pct: Custom stop-loss percentage (e.g., 0.04 for 4%). If None, uses default.
            signal_features: Dict of signal features for ML learning (RSI, MACD, etc.)
            
        Returns:
            Position if successful, None otherwise
        """
        # Calculate position size
        if amount is None:
            max_value = self.portfolio.cash * self.max_position_size
            amount = max_value / price
        
        total_cost = price * amount
        
        # Check if we have enough cash
        if total_cost > self.portfolio.cash:
            self.logger.warning(f"[PAPER] Insufficient funds for {symbol}: need ${total_cost:.2f}, have ${self.portfolio.cash:.2f}")
            return None
        
        # Check if already in position
        if symbol in self.portfolio.positions:
            self.logger.warning(f"[PAPER] Already in position for {symbol}")
            return None
        
        # Use dynamic stop-loss if provided, otherwise default
        sl_pct = stop_loss_pct if stop_loss_pct is not None else self.default_stop_loss
        
        # Execute buy
        self.portfolio.cash -= total_cost
        
        position = Position(
            symbol=symbol,
            entry_price=price,
            amount=amount,
            entry_time=datetime.utcnow(),
            side="BUY",
            stop_loss=price * (1 - sl_pct),
            take_profit=price * (1 + self.default_take_profit),
            last_movement_time=datetime.utcnow(),
            signal_features=signal_features  # Store for ML learning
        )
        
        self.portfolio.positions[symbol] = position
        self.price_cache[symbol] = price
        
        # Record entry for auto-learning
        if self.auto_learner and signal_features:
            self.auto_learner.record_entry(
                symbol=symbol,
                price=price,
                signal_type=signal_features.get("signal_type", ""),
                signal_score=signal_features.get("score", 0),
                change_percent=signal_features.get("change_percent", 0),
                volume_usd=signal_features.get("volume_usd", 0),
                rsi=signal_features.get("rsi", 50),
                stoch_rsi=signal_features.get("stoch_rsi", 50),
                macd_signal=signal_features.get("macd_signal", "neutral"),
                ema_trend=signal_features.get("ema_trend", "neutral"),
                atr_percent=signal_features.get("atr_percent", 0),
                btc_correlation=signal_features.get("btc_correlation", 0),
                volatility_24h=signal_features.get("volatility_24h", 0)
            )
        
        self.logger.info(
            f"[PAPER] BUY {symbol} @ ${price:.6f} | "
            f"Amount: {amount:.4f} | Cost: ${total_cost:.2f} | "
            f"SL: {sl_pct*100:.1f}% | Reason: {reason}"
        )
        
        # Send Telegram notification
        await self._notify_telegram_trade_opened(symbol, price, total_cost, reason)
        
        await self._save_state()
        return position
    
    async def sell(
        self, 
        symbol: str, 
        price: float,
        reason: str = "Manual"
    ) -> Optional[Trade]:
        """
        Execute a simulated SELL order (close position)
        
        Args:
            symbol: Trading pair
            price: Exit price
            reason: Reason for closing
            
        Returns:
            Trade record if successful
        """
        if symbol not in self.portfolio.positions:
            self.logger.warning(f"[PAPER] No position to sell for {symbol}")
            return None
        
        position = self.portfolio.positions[symbol]
        
        # Calculate P&L
        exit_value = price * position.amount
        entry_value = position.entry_price * position.amount
        pnl = exit_value - entry_value
        pnl_percent = ((price - position.entry_price) / position.entry_price) * 100
        
        # Update portfolio
        self.portfolio.cash += exit_value
        del self.portfolio.positions[symbol]
        
        # Update stats
        self.trade_counter += 1
        self.portfolio.total_trades += 1
        if pnl > 0:
            self.portfolio.winning_trades += 1
        else:
            self.portfolio.losing_trades += 1
        
        # Record trade
        trade = Trade(
            id=f"T{self.trade_counter:05d}",
            symbol=symbol,
            side="SELL",
            entry_price=position.entry_price,
            exit_price=price,
            amount=position.amount,
            entry_time=position.entry_time,
            exit_time=datetime.utcnow(),
            pnl=pnl,
            pnl_percent=pnl_percent,
            reason=reason
        )
        
        # Record exit for auto-learning
        if self.auto_learner:
            self.auto_learner.record_exit(
                symbol=symbol,
                exit_price=price,
                pnl_percent=pnl_percent,
                exit_reason=reason
            )
        
        self.portfolio.trade_history.append(trade)
        
        # Log result
        pnl_emoji = "+" if pnl > 0 else ""
        self.logger.info(
            f"[PAPER] SELL {symbol} @ ${price:.6f} | "
            f"PnL: {pnl_emoji}${pnl:.2f} ({pnl_emoji}{pnl_percent:.2f}%) | "
            f"Reason: {reason}"
        )
        
        # Send Telegram notification
        await self._notify_telegram_trade_closed(symbol, position.entry_price, price, pnl, pnl_percent, reason)
        
        await self._save_state()
        return trade
    
    async def update_prices(self, prices: Dict[str, float]):
        """
        Update price cache and check trailing stop-loss / scaled take-profits
        
        Features:
        - Trailing Stop-Loss: Follows price up, locks in profits
        - Scaled Take-Profits: Sell 25% at +10%, 50% at +20%, rest at +30%
        
        Args:
            prices: Dict of symbol -> current price
        """
        self.price_cache.update(prices)
        
        positions_to_close = []
        partial_sells = []
        
        for symbol, position in self.portfolio.positions.items():
            if symbol not in prices:
                continue
                
            current_price = prices[symbol]
            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            
            # Initialize original amount if not set
            if position.original_amount is None:
                position.original_amount = position.amount
            
            # Initialize last_movement_time if not set
            if position.last_movement_time is None:
                position.last_movement_time = position.entry_time
            
            # Check for significant price movement (> 1%)
            if abs(pnl_pct) > 1.0:
                position.last_movement_time = datetime.utcnow()
            
            # ===== TIMEOUT FOR STAGNANT POSITIONS - SWING TRADE v6.0 =====
            # Swing trades can hold longer - 12h timeout (was 3h)
            time_since_movement = (datetime.utcnow() - position.last_movement_time).total_seconds()
            hours_since_movement = time_since_movement / 3600
            
            if hours_since_movement >= 12 and abs(pnl_pct) < 1.5:  # 12h timeout, 1.5% threshold
                positions_to_close.append((symbol, current_price, f"Timeout: stagnant for {hours_since_movement:.1f}h (PnL: {pnl_pct:.2f}%)"))
                continue  # Skip other checks
            
            # Update highest price for trailing stop
            if position.highest_price is None or current_price > position.highest_price:
                position.highest_price = current_price
            
            # ===== TRAILING STOP-LOSS - SWING TRADE v6.0 (BACKTESTED) =====
            # Activate trailing stop after +5% profit (wider for swing trades)
            if pnl_pct >= 5.0 and not position.trailing_activated:
                position.trailing_activated = True
                self.logger.info(f"[SWING] 🔒 Trailing stop activated for {symbol} at +{pnl_pct:.1f}%")
            
            # Calculate trailing stop level (3% from highest for swing trades)
            if position.trailing_activated and position.highest_price:
                trailing_stop_price = position.highest_price * (1 - position.trailing_stop_pct)
                
                # Update stop-loss to trailing level if higher
                if trailing_stop_price > (position.stop_loss or 0):
                    old_sl = position.stop_loss
                    position.stop_loss = trailing_stop_price
                    self.logger.debug(f"[SWING] 📈 {symbol} SL moved: ${old_sl:.6f} → ${trailing_stop_price:.6f}")
            
            # ===== SCALED TAKE-PROFITS - SWING TRADE v6.0 (BACKTESTED) =====
            # From backtest: TP=10%, SL=5% gives 94.7% win rate
            
            # TP1: +4% - Sell 20% (lock early profits)
            if pnl_pct >= 4.0 and not position.tp1_hit and position.amount > 0:
                sell_amount = position.original_amount * 0.20
                if sell_amount > 0 and position.amount >= sell_amount:
                    partial_sells.append((symbol, current_price, sell_amount, "TP1 (+4%)", 1))
                    position.tp1_hit = True
            
            # TP2: +7% - Sell 30% of original
            if pnl_pct >= 7.0 and not position.tp2_hit and position.amount > 0:
                sell_amount = position.original_amount * 0.30
                if sell_amount > 0 and position.amount >= sell_amount:
                    partial_sells.append((symbol, current_price, sell_amount, "TP2 (+7%)", 2))
                    position.tp2_hit = True
            
            # TP3: +10% - Sell remaining (backtest validated target)
            if pnl_pct >= 10.0 and not position.tp3_hit and position.amount > 0:
                positions_to_close.append((symbol, current_price, "TP3 (+10%) - Full Exit"))
                position.tp3_hit = True
                continue  # Skip stop-loss check
            
            # ===== STOP-LOSS CHECK =====
            if position.stop_loss and current_price <= position.stop_loss:
                reason = "Trailing Stop" if position.trailing_activated else "Stop Loss"
                positions_to_close.append((symbol, current_price, reason))
        
        # Execute partial sells
        for symbol, price, amount, reason, tp_level in partial_sells:
            await self._partial_sell(symbol, price, amount, reason)
        
        # Close full positions
        for symbol, price, reason in positions_to_close:
            await self.sell(symbol, price, reason)
    
    async def _partial_sell(self, symbol: str, price: float, amount: float, reason: str):
        """Execute a partial sell (for scaled take-profits)"""
        if symbol not in self.portfolio.positions:
            return
        
        position = self.portfolio.positions[symbol]
        
        if amount > position.amount:
            amount = position.amount
        
        # Calculate partial P&L
        exit_value = price * amount
        entry_value = position.entry_price * amount
        pnl = exit_value - entry_value
        pnl_percent = ((price - position.entry_price) / position.entry_price) * 100
        
        # Update portfolio
        self.portfolio.cash += exit_value
        position.amount -= amount
        
        self.logger.info(
            f"[PAPER] 📊 PARTIAL SELL {symbol} @ ${price:.6f} | "
            f"Amount: {amount:.4f} | PnL: +${pnl:.2f} (+{pnl_percent:.1f}%) | "
            f"Reason: {reason}"
        )
        
        # If position is now empty, remove it
        if position.amount <= 0:
            del self.portfolio.positions[symbol]
            self.portfolio.total_trades += 1
            self.portfolio.winning_trades += 1
        
        await self._save_state()
    
    async def simulate_listing_trade(
        self, 
        symbol: str,
        listing_price: float,
        peak_multiplier: float = 2.0,
        success_rate: float = 0.6
    ) -> Optional[Trade]:
        """
        Simulate a new listing trade
        
        This simulates what happens when a new token is listed:
        - Buy at listing price
        - Price either pumps (success) or dumps (failure)
        - Sell at simulated exit price
        
        Args:
            symbol: Token symbol
            listing_price: Initial listing price
            peak_multiplier: Max price increase on success
            success_rate: Probability of successful trade
        """
        # Buy at listing
        position = await self.buy(symbol, listing_price, reason="New Listing")
        if not position:
            return None
        
        # Simulate price movement (for training purposes)
        await asyncio.sleep(1)  # Small delay
        
        is_success = random.random() < success_rate
        
        if is_success:
            # Successful listing - price pumps
            price_change = random.uniform(1.2, peak_multiplier)
            exit_price = listing_price * price_change
            reason = "Take Profit (Listing Pump)"
        else:
            # Failed listing - price dumps
            price_change = random.uniform(0.5, 0.9)
            exit_price = listing_price * price_change
            reason = "Stop Loss (Listing Dump)"
        
        # Sell
        trade = await self.sell(symbol, exit_price, reason)
        
        return trade
    
    async def handle_new_listing(
        self,
        symbol: str,
        exchange: str = "binance",
        amount_usd: float = 500.0  # Increased for new listings (high confidence)
    ) -> Optional["ListingTrade"]:
        """
        Handle a new token listing - buy with REAL price from API
        
        Args:
            symbol: Token symbol (e.g., "PEPE")
            exchange: Exchange name
            amount_usd: Amount in USD to invest
            
        Returns:
            ListingTrade object with trade details
        """
        # Build the trading pair
        trading_pair = f"{symbol}USDT"
        
        # Fetch REAL price from Binance API
        listing_price = await self._fetch_real_price(trading_pair)
        
        if listing_price is None or listing_price <= 0:
            self.logger.warning(f"[LISTING] Could not get price for {trading_pair}, trying alternatives...")
            # Try with different quote currencies
            for quote in ["BUSD", "BTC", "ETH"]:
                alt_pair = f"{symbol}{quote}"
                listing_price = await self._fetch_real_price(alt_pair)
                if listing_price and listing_price > 0:
                    trading_pair = alt_pair
                    break
            
            if listing_price is None or listing_price <= 0:
                self.logger.error(f"[LISTING] ❌ Cannot find price for {symbol} on any pair")
                return None
        
        self.logger.info(f"[LISTING] 🆕 NEW LISTING DETECTED: {symbol}")
        self.logger.info(f"[LISTING] 💰 Real price from API: ${listing_price:.8f}")
        
        # Calculate amount based on USD
        amount = amount_usd / listing_price
        
        # Execute buy with special stop loss for new listings (more volatile)
        position = await self.buy(
            symbol=trading_pair,
            price=listing_price,
            amount=amount,
            reason=f"🆕 NEW LISTING on {exchange}",
            stop_loss_pct=0.15  # 15% SL for new listings (more volatile)
        )
        
        if not position:
            self.logger.error(f"[LISTING] ❌ Failed to buy {symbol}")
            return None
        
        self.logger.info(f"[LISTING] ✅ Bought {amount:.4f} {symbol} @ ${listing_price:.8f} = ${amount_usd:.2f}")
        
        # Return trade info
        return ListingTrade(
            symbol=symbol,
            exchange=exchange,
            entry_price=listing_price,
            amount=amount,
            value_usd=amount_usd,
            timestamp=datetime.utcnow()
        )
    
    async def _fetch_real_price(self, symbol: str) -> Optional[float]:
        """
        Fetch real price from Binance API
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            
        Returns:
            Current price or None if not available
        """
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        return float(data.get("price", 0))
                    else:
                        return None
        except Exception as e:
            self.logger.debug(f"[API] Price fetch error for {symbol}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics"""
        return {
            "initial_capital": self.portfolio.initial_capital,
            "current_value": self.portfolio.total_value,
            "cash": self.portfolio.cash,
            "total_pnl": self.portfolio.total_pnl,
            "total_pnl_percent": self.portfolio.total_pnl_percent,
            "total_trades": self.portfolio.total_trades,
            "winning_trades": self.portfolio.winning_trades,
            "losing_trades": self.portfolio.losing_trades,
            "win_rate": self.portfolio.win_rate,
            "open_positions": len(self.portfolio.positions)
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current portfolio status"""
        return {
            "cash": round(self.portfolio.cash, 2),
            "positions_count": len(self.portfolio.positions),
            "positions_value": round(sum(p.value for p in self.portfolio.positions.values()), 2),
            "total_value": round(self.portfolio.total_value, 2),
            "total_pnl": round(self.portfolio.total_pnl, 2),
            "total_pnl_percent": round(self.portfolio.total_pnl_percent, 2),
            "total_trades": self.portfolio.total_trades,
            "winning_trades": self.portfolio.winning_trades,
            "losing_trades": self.portfolio.losing_trades,
            "win_rate": round(self.portfolio.win_rate, 1),
            "positions": {
                symbol: {
                    "entry_price": p.entry_price,
                    "amount": p.amount,
                    "value": round(p.value, 2),
                    "entry_time": p.entry_time.isoformat()
                }
                for symbol, p in self.portfolio.positions.items()
            }
        }
    
    def print_status(self):
        """Print formatted portfolio status"""
        status = self.get_status()
        
        pnl_sign = "+" if status["total_pnl"] >= 0 else ""
        
        self.logger.info("=" * 50)
        self.logger.info("[PAPER] PORTFOLIO STATUS")
        self.logger.info("=" * 50)
        self.logger.info(f"  Cash:          ${status['cash']:,.2f}")
        self.logger.info(f"  Positions:     {status['positions_count']} (${status['positions_value']:,.2f})")
        self.logger.info(f"  Total Value:   ${status['total_value']:,.2f}")
        self.logger.info(f"  P&L:           {pnl_sign}${status['total_pnl']:,.2f} ({pnl_sign}{status['total_pnl_percent']:.2f}%)")
        self.logger.info(f"  Trades:        {status['total_trades']} (Win: {status['winning_trades']}, Loss: {status['losing_trades']})")
        self.logger.info(f"  Win Rate:      {status['win_rate']:.1f}%")
        self.logger.info("=" * 50)
    
    async def _save_state(self):
        """Save portfolio state to file"""
        try:
            state = {
                "portfolio": {
                    "initial_capital": self.portfolio.initial_capital,
                    "cash": self.portfolio.cash,
                    "total_trades": self.portfolio.total_trades,
                    "winning_trades": self.portfolio.winning_trades,
                    "losing_trades": self.portfolio.losing_trades,
                },
                "positions": {
                    symbol: {
                        "entry_price": p.entry_price,
                        "amount": p.amount,
                        "entry_time": p.entry_time.isoformat(),
                        "stop_loss": p.stop_loss,
                        "take_profit": p.take_profit
                    }
                    for symbol, p in self.portfolio.positions.items()
                },
                "trade_history": [
                    {
                        "id": t.id,
                        "symbol": t.symbol,
                        "pnl": t.pnl,
                        "pnl_percent": t.pnl_percent,
                        "reason": t.reason,
                        "exit_time": t.exit_time.isoformat()
                    }
                    for t in self.portfolio.trade_history[-100:]  # Keep last 100
                ],
                "trade_counter": self.trade_counter,
                "saved_at": datetime.utcnow().isoformat()
            }
            
            os.makedirs("data", exist_ok=True)
            with open("data/paper_portfolio.json", "w") as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"[PAPER] Failed to save state: {e}")
    
    async def _load_state(self):
        """Load portfolio state from file"""
        try:
            if not os.path.exists("data/paper_portfolio.json"):
                return
            
            with open("data/paper_portfolio.json", "r") as f:
                state = json.load(f)
            
            # Restore portfolio
            self.portfolio.cash = state["portfolio"]["cash"]
            self.portfolio.total_trades = state["portfolio"]["total_trades"]
            self.portfolio.winning_trades = state["portfolio"]["winning_trades"]
            self.portfolio.losing_trades = state["portfolio"]["losing_trades"]
            self.trade_counter = state.get("trade_counter", 0)
            
            # Restore positions
            for symbol, pos_data in state.get("positions", {}).items():
                self.portfolio.positions[symbol] = Position(
                    symbol=symbol,
                    entry_price=pos_data["entry_price"],
                    amount=pos_data["amount"],
                    entry_time=datetime.fromisoformat(pos_data["entry_time"]),
                    stop_loss=pos_data.get("stop_loss"),
                    take_profit=pos_data.get("take_profit")
                )
            
            self.logger.info(f"[PAPER] Restored portfolio: ${self.portfolio.total_value:,.2f}")
            
        except Exception as e:
            self.logger.error(f"[PAPER] Failed to load state: {e}")
    
    async def _notify_telegram_trade_opened(self, symbol: str, price: float, cost: float, reason: str):
        """Send Telegram notification for opened trade"""
        try:
            from src.notifications.telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            if bot.is_enabled:
                await bot.notify_trade_opened(symbol, "BUY", price, cost, reason)
        except Exception as e:
            self.logger.debug(f"[PAPER] Telegram notification failed: {e}")
    
    async def _notify_telegram_trade_closed(self, symbol: str, entry: float, exit: float, pnl: float, pnl_pct: float, reason: str):
        """Send Telegram notification for closed trade"""
        try:
            from src.notifications.telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            if bot.is_enabled:
                await bot.notify_trade_closed(symbol, entry, exit, pnl, pnl_pct, reason)
        except Exception as e:
            self.logger.debug(f"[PAPER] Telegram notification failed: {e}")
