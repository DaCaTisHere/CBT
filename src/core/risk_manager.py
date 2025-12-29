"""
Risk Manager - Global risk management and position limits

Responsibilities:
- Enforce position size limits
- Monitor daily loss limits
- Track drawdown
- Implement stop-loss logic
- Circuit breakers for extreme volatility
"""

from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime, timedelta
import asyncio

from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


class RiskManager:
    """
    Global risk management system
    """
    
    def __init__(self):
        """Initialize risk manager"""
        self.logger = logger
        
        # Portfolio tracking
        self.initial_capital = Decimal("0")
        self.current_capital = Decimal("0")
        self.daily_start_capital = Decimal("0")
        self.peak_capital = Decimal("0")
        
        # Risk limits
        self.max_position_size_pct = Decimal(str(settings.MAX_POSITION_SIZE_PCT))
        self.max_daily_loss_pct = Decimal(str(settings.MAX_DAILY_LOSS_PCT))
        self.stop_loss_pct = Decimal(str(settings.STOP_LOSS_PCT))
        
        # Trading state
        self.trading_enabled = True
        self.daily_loss_exceeded = False
        self.last_reset_date = datetime.utcnow().date()
        
        # Open positions tracking
        self.open_positions: Dict[str, Dict] = {}
        
        self.logger.info("[RISK] Risk Manager initialized")
        self.logger.info(f"   Max position size: {self.max_position_size_pct}%")
        self.logger.info(f"   Max daily loss: {self.max_daily_loss_pct}%")
        self.logger.info(f"   Stop loss: {self.stop_loss_pct}%")
    
    async def initialize(self, wallet_manager=None):
        """Initialize risk manager with current capital from wallet or config"""
        from src.core.config import settings
        import os
        
        # Try to get real balance from exchange if available
        capital = Decimal("10000")  # Default fallback
        
        if not settings.SIMULATION_MODE and wallet_manager:
            try:
                # Fetch real USDT balance from Binance
                import ccxt.async_support as ccxt
                if settings.BINANCE_API_KEY and settings.BINANCE_SECRET:
                    exchange = ccxt.binance({
                        'apiKey': settings.BINANCE_API_KEY,
                        'secret': settings.BINANCE_SECRET,
                        'enableRateLimit': True,
                    })
                    balance = await exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    await exchange.close()
                    
                    if usdt_balance > 0:
                        capital = Decimal(str(usdt_balance))
                        self.logger.info(f"[WALLET] Real USDT balance: ${capital}")
            except Exception as e:
                self.logger.warning(f"[WALLET] Could not fetch real balance: {e}")
                self.logger.info("[WALLET] Using default capital for simulation")
        
        # Load from saved state if exists
        state_file = "data/risk_state.json"
        if os.path.exists(state_file):
            try:
                import json
                with open(state_file, "r") as f:
                    state = json.load(f)
                    saved_capital = Decimal(str(state.get("current_capital", capital)))
                    if saved_capital > 0:
                        capital = saved_capital
                        self.logger.info(f"[RISK] Restored capital from state: ${capital}")
            except Exception as e:
                self.logger.warning(f"[RISK] Could not load state: {e}")
        
        self.initial_capital = capital
        self.current_capital = capital
        self.daily_start_capital = capital
        self.peak_capital = capital
        
        self.logger.info(f"[OK] Initial capital: ${self.initial_capital}")
    
    async def check_can_trade(self, strategy: str, amount: Decimal) -> tuple[bool, str]:
        """
        Check if a trade can be executed
        
        Args:
            strategy: Strategy name
            amount: Trade amount in USD
        
        Returns:
            (can_trade, reason)
        """
        # Check if trading is globally enabled
        if not self.trading_enabled:
            return False, "Trading globally disabled"
        
        # Check daily loss limit
        if self.daily_loss_exceeded:
            return False, f"Daily loss limit exceeded (-{self.max_daily_loss_pct}%)"
        
        # Check position size limit
        max_position = self.current_capital * (self.max_position_size_pct / Decimal("100"))
        if amount > max_position:
            return False, f"Position size {amount} exceeds limit {max_position}"
        
        return True, "OK"
    
    async def check_global_limits(self):
        """Check global risk limits"""
        # Reset daily limits if new day
        current_date = datetime.utcnow().date()
        if current_date > self.last_reset_date:
            await self._reset_daily_limits()
        
        # Check daily loss
        daily_pnl = self.current_capital - self.daily_start_capital
        daily_pnl_pct = (daily_pnl / self.daily_start_capital) * Decimal("100")
        
        if daily_pnl_pct <= -self.max_daily_loss_pct:
            if not self.daily_loss_exceeded:
                self.daily_loss_exceeded = True
                self.trading_enabled = False
                self.logger.critical(f"[ALERT] DAILY LOSS LIMIT EXCEEDED: {daily_pnl_pct:.2f}%")
                self.logger.critical("[HALTED] TRADING HALTED UNTIL TOMORROW")
                # TODO: Send alert (Telegram, email, etc.)
        
        # Update peak capital (for drawdown calc)
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        # Calculate max drawdown
        drawdown = ((self.peak_capital - self.current_capital) / self.peak_capital) * Decimal("100")
        if drawdown > Decimal("30"):  # 30% max drawdown threshold
            self.logger.critical(f"[ALERT] MAX DRAWDOWN EXCEEDED: {drawdown:.2f}%")
            # Circuit breaker logic here
    
    async def _reset_daily_limits(self):
        """Reset daily tracking at start of new day"""
        self.logger.info("[DAILY] New day - resetting daily limits")
        self.daily_start_capital = self.current_capital
        self.daily_loss_exceeded = False
        self.trading_enabled = True
        self.last_reset_date = datetime.utcnow().date()
    
    def register_position(self, position_id: str, strategy: str, symbol: str, 
                         amount: Decimal, entry_price: Decimal, side: str):
        """Register a new open position"""
        self.open_positions[position_id] = {
            "strategy": strategy,
            "symbol": symbol,
            "amount": amount,
            "entry_price": entry_price,
            "side": side,
            "opened_at": datetime.utcnow(),
            "stop_loss": self._calculate_stop_loss(entry_price, side),
        }
        
        self.logger.info(f"[OPEN] Position opened: {position_id} ({symbol}) ${amount}")
    
    def _calculate_stop_loss(self, entry_price: Decimal, side: str) -> Decimal:
        """Calculate stop loss price"""
        if side == "LONG":
            return entry_price * (Decimal("1") - self.stop_loss_pct / Decimal("100"))
        else:  # SHORT
            return entry_price * (Decimal("1") + self.stop_loss_pct / Decimal("100"))
    
    def close_position(self, position_id: str, exit_price: Decimal, pnl: Decimal):
        """Close a position and update capital"""
        if position_id not in self.open_positions:
            self.logger.warning(f"Position {position_id} not found")
            return
        
        position = self.open_positions.pop(position_id)
        self.current_capital += pnl
        
        pnl_pct = (pnl / position["amount"]) * Decimal("100")
        self.logger.info(f"[CLOSE] Position closed: {position_id} | PnL: ${pnl} ({pnl_pct:.2f}%)")
    
    def should_stop_loss(self, position_id: str, current_price: Decimal) -> bool:
        """Check if position should be stopped out"""
        if position_id not in self.open_positions:
            return False
        
        position = self.open_positions[position_id]
        stop_loss = position["stop_loss"]
        
        if position["side"] == "LONG":
            return current_price <= stop_loss
        else:  # SHORT
            return current_price >= stop_loss
    
    async def get_metrics(self) -> Dict:
        """Get current risk metrics"""
        total_pnl = self.current_capital - self.initial_capital
        total_pnl_pct = (total_pnl / self.initial_capital) * Decimal("100")
        
        daily_pnl = self.current_capital - self.daily_start_capital
        daily_pnl_pct = (daily_pnl / self.daily_start_capital) * Decimal("100")
        
        drawdown = ((self.peak_capital - self.current_capital) / self.peak_capital) * Decimal("100")
        
        return {
            "current_capital": float(self.current_capital),
            "total_pnl": float(total_pnl),
            "total_pnl_pct": float(total_pnl_pct),
            "daily_pnl": float(daily_pnl),
            "daily_pnl_pct": float(daily_pnl_pct),
            "max_drawdown_pct": float(drawdown),
            "trading_enabled": self.trading_enabled,
            "open_positions": len(self.open_positions),
        }
    
    async def save_state(self):
        """Persist current state to disk for recovery"""
        import json
        import os
        
        try:
            os.makedirs("data", exist_ok=True)
            state = {
                "initial_capital": float(self.initial_capital),
                "current_capital": float(self.current_capital),
                "daily_start_capital": float(self.daily_start_capital),
                "peak_capital": float(self.peak_capital),
                "trading_enabled": self.trading_enabled,
                "daily_loss_exceeded": self.daily_loss_exceeded,
                "last_reset_date": self.last_reset_date.isoformat(),
                "open_positions": {
                    k: {**v, "opened_at": v["opened_at"].isoformat()}
                    for k, v in self.open_positions.items()
                },
                "saved_at": datetime.utcnow().isoformat()
            }
            
            with open("data/risk_state.json", "w") as f:
                json.dump(state, f, indent=2, default=str)
                
            self.logger.debug("[RISK] State saved")
        except Exception as e:
            self.logger.error(f"[RISK] Failed to save state: {e}")

