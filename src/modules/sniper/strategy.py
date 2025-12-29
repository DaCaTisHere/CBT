"""
Sniper Trading Strategy

Defines entry/exit logic, position sizing, and risk management for sniper trades.
"""

import asyncio
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

from src.core.risk_manager import RiskManager
from src.utils.logger import get_logger


logger = get_logger(__name__)


class SniperStrategy:
    """
    Trading strategy for sniper bot
    
    Handles:
    - Entry decision logic
    - Position sizing
    - Take profit / Stop loss calculation
    - Exit timing
    """
    
    # Default parameters
    DEFAULT_ENTRY_AMOUNT_USD = 100.0  # Initial buy amount
    DEFAULT_TAKE_PROFIT_PCT = 100.0  # 2x (100% gain)
    DEFAULT_STOP_LOSS_PCT = 30.0  # -30% max loss
    MAX_HOLD_TIME_HOURS = 24  # Close position after 24h
    
    # Scaling take profits (partial exits)
    TAKE_PROFIT_LEVELS = [
        (50, 25),   # At +50%, sell 25%
        (100, 50),  # At +100% (2x), sell 50%
        (200, 75),  # At +200% (3x), sell 75%
    ]
    
    def __init__(self, risk_manager: RiskManager):
        """
        Initialize strategy
        
        Args:
            risk_manager: Risk manager instance
        """
        self.risk_manager = risk_manager
        self.logger = logger
        
        # Strategy parameters (can be adjusted)
        self.entry_amount_usd = self.DEFAULT_ENTRY_AMOUNT_USD
        self.take_profit_pct = self.DEFAULT_TAKE_PROFIT_PCT
        self.stop_loss_pct = self.DEFAULT_STOP_LOSS_PCT
        self.max_hold_hours = self.MAX_HOLD_TIME_HOURS
        
        self.logger.info(f"[STRATEGY] Sniper strategy initialized")
        self.logger.info(f"   Entry amount: ${self.entry_amount_usd}")
        self.logger.info(f"   Take profit: +{self.take_profit_pct}%")
        self.logger.info(f"   Stop loss: -{self.stop_loss_pct}%")
    
    async def should_enter(
        self,
        token_address: str,
        safety_score: int,
        liquidity_usd: float,
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Decide if we should enter a trade
        
        Args:
            token_address: Token contract address
            safety_score: Safety score from contract analyzer (0-100)
            liquidity_usd: Liquidity in USD
            current_price: Current token price
        
        Returns:
            Tuple of (should_enter: bool, reason: Optional[str])
        """
        # Rule 1: Safety score must be >= 70
        if safety_score < 70:
            return False, f"Safety score too low ({safety_score})"
        
        # Rule 2: Minimum liquidity
        if liquidity_usd < 5000:
            return False, f"Liquidity too low (${liquidity_usd:.0f})"
        
        # Rule 3: Price must be reasonable (not too high)
        if current_price > 1000:
            return False, f"Price too high (${current_price})"
        
        # Rule 4: Check risk limits
        can_trade, reason = await self.risk_manager.check_can_trade(
            strategy="sniper",
            amount_usd=Decimal(self.entry_amount_usd)
        )
        
        if not can_trade:
            return False, f"Risk limit: {reason}"
        
        # All checks passed
        return True, None
    
    def calculate_position_size(
        self,
        token_price: float,
        available_capital: float
    ) -> Dict[str, Any]:
        """
        Calculate optimal position size
        
        Args:
            token_price: Current token price
            available_capital: Available capital in USD
        
        Returns:
            Dict with position size details
        """
        # Use configured entry amount, but cap at available capital
        entry_usd = min(self.entry_amount_usd, available_capital * 0.1)  # Max 10% of capital
        
        # Calculate token amount
        token_amount = entry_usd / token_price
        
        return {
            "entry_usd": entry_usd,
            "token_amount": token_amount,
            "token_price": token_price,
        }
    
    def calculate_exit_levels(
        self,
        entry_price: float,
        token_amount: float
    ) -> Dict[str, Any]:
        """
        Calculate take profit and stop loss levels
        
        Args:
            entry_price: Entry price
            token_amount: Token amount held
        
        Returns:
            Dict with exit levels
        """
        # Calculate take profit price
        take_profit_price = entry_price * (1 + self.take_profit_pct / 100)
        
        # Calculate stop loss price
        stop_loss_price = entry_price * (1 - self.stop_loss_pct / 100)
        
        # Calculate scaling TP levels
        scaling_levels = []
        for pct_gain, pct_sell in self.TAKE_PROFIT_LEVELS:
            price = entry_price * (1 + pct_gain / 100)
            amount = token_amount * (pct_sell / 100)
            
            scaling_levels.append({
                "price": price,
                "pct_gain": pct_gain,
                "sell_amount": amount,
                "sell_pct": pct_sell
            })
        
        return {
            "entry_price": entry_price,
            "take_profit_price": take_profit_price,
            "stop_loss_price": stop_loss_price,
            "scaling_levels": scaling_levels,
            "max_hold_until": datetime.utcnow() + timedelta(hours=self.max_hold_hours)
        }
    
    async def should_exit(
        self,
        position: Dict[str, Any],
        current_price: float,
        current_time: datetime
    ) -> Tuple[bool, str, float]:
        """
        Decide if we should exit position
        
        Args:
            position: Position dict with entry data
            current_price: Current token price
            current_time: Current time
        
        Returns:
            Tuple of (should_exit: bool, reason: str, sell_percentage: float)
        """
        entry_price = position["entry_price"]
        entry_time = position.get("entry_time", datetime.utcnow())
        max_hold_until = position.get("max_hold_until", datetime.utcnow() + timedelta(hours=24))
        
        # Calculate current PnL
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Rule 1: Stop loss triggered
        if pnl_pct <= -self.stop_loss_pct:
            return True, f"Stop loss triggered ({pnl_pct:.1f}%)", 100.0
        
        # Rule 2: Take profit triggered
        if pnl_pct >= self.take_profit_pct:
            return True, f"Take profit triggered ({pnl_pct:.1f}%)", 100.0
        
        # Rule 3: Scaling take profits
        for level in self.TAKE_PROFIT_LEVELS:
            pct_gain, pct_sell = level
            if pnl_pct >= pct_gain and pnl_pct < (pct_gain + 10):  # Within 10% of level
                return True, f"Scaling TP at {pct_gain}%", float(pct_sell)
        
        # Rule 4: Max hold time exceeded
        if current_time >= max_hold_until:
            return True, f"Max hold time exceeded ({self.max_hold_hours}h)", 100.0
        
        # Hold position
        return False, "Holding", 0.0
    
    def adjust_for_volatility(
        self,
        current_volatility: float,
        base_stop_loss: float
    ) -> float:
        """
        Adjust stop loss based on volatility
        
        Higher volatility = wider stop loss
        
        Args:
            current_volatility: Current price volatility (e.g., 0.5 = 50%)
            base_stop_loss: Base stop loss percentage
        
        Returns:
            Adjusted stop loss percentage
        """
        # Increase stop loss by volatility factor
        volatility_multiplier = 1 + (current_volatility / 2)
        adjusted_stop_loss = base_stop_loss * volatility_multiplier
        
        # Cap at 50%
        return min(adjusted_stop_loss, 50.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics"""
        return {
            "entry_amount_usd": self.entry_amount_usd,
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "max_hold_hours": self.max_hold_hours,
            "scaling_levels": self.TAKE_PROFIT_LEVELS,
        }
