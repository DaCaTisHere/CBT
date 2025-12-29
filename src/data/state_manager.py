"""
State Manager - Persistent state storage

Saves and loads bot state from database/file to survive restarts.
"""

import json
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from src.utils.logger import get_logger
from src.core.config import settings

logger = get_logger(__name__)


@dataclass
class BotState:
    """Complete bot state"""
    # Portfolio
    initial_capital: float = 10000.0
    cash: float = 10000.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Positions (serialized)
    positions: Dict[str, Dict] = None
    
    # Trade history (last 100)
    trade_history: List[Dict] = None
    
    # Counters
    trade_counter: int = 0
    signals_processed: int = 0
    
    # Timestamps
    started_at: str = None
    last_save: str = None
    
    def __post_init__(self):
        if self.positions is None:
            self.positions = {}
        if self.trade_history is None:
            self.trade_history = []
        if self.started_at is None:
            self.started_at = datetime.utcnow().isoformat()


class StateManager:
    """
    Manages persistent state storage
    
    Features:
    - Auto-save every N minutes
    - Load state on startup
    - Crash recovery
    - Multiple storage backends (file, database)
    """
    
    STATE_FILE = "data/bot_state.json"
    BACKUP_FILE = "data/bot_state_backup.json"
    AUTO_SAVE_INTERVAL = 60  # seconds
    
    def __init__(self):
        self.logger = logger
        self.state = BotState()
        self.is_running = False
        self._save_task: Optional[asyncio.Task] = None
        
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
        
        self.logger.info("[STATE] State Manager initialized")
    
    async def load(self) -> BotState:
        """Load state from storage"""
        try:
            # Try primary file
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, "r") as f:
                    data = json.load(f)
                
                self.state = BotState(**data)
                self.logger.info(f"[STATE] Loaded state from {self.STATE_FILE}")
                self.logger.info(f"[STATE]   Cash: ${self.state.cash:,.2f}")
                self.logger.info(f"[STATE]   Positions: {len(self.state.positions)}")
                self.logger.info(f"[STATE]   Trades: {self.state.total_trades}")
                return self.state
            
            # Try backup
            elif os.path.exists(self.BACKUP_FILE):
                with open(self.BACKUP_FILE, "r") as f:
                    data = json.load(f)
                
                self.state = BotState(**data)
                self.logger.info(f"[STATE] Loaded state from backup")
                return self.state
            
            else:
                self.logger.info("[STATE] No saved state found, starting fresh")
                return self.state
                
        except Exception as e:
            self.logger.error(f"[STATE] Load error: {e}")
            return self.state
    
    async def save(self) -> bool:
        """Save current state to storage"""
        try:
            # Update timestamp
            self.state.last_save = datetime.utcnow().isoformat()
            
            # Create backup of existing file
            if os.path.exists(self.STATE_FILE):
                os.replace(self.STATE_FILE, self.BACKUP_FILE)
            
            # Save new state
            with open(self.STATE_FILE, "w") as f:
                json.dump(asdict(self.state), f, indent=2, default=str)
            
            self.logger.debug(f"[STATE] State saved")
            return True
            
        except Exception as e:
            self.logger.error(f"[STATE] Save error: {e}")
            return False
    
    async def start_auto_save(self):
        """Start auto-save background task"""
        self.is_running = True
        self._save_task = asyncio.create_task(self._auto_save_loop())
        self.logger.info(f"[STATE] Auto-save started (every {self.AUTO_SAVE_INTERVAL}s)")
    
    async def stop_auto_save(self):
        """Stop auto-save and do final save"""
        self.is_running = False
        
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        
        # Final save
        await self.save()
        self.logger.info("[STATE] Auto-save stopped, final state saved")
    
    async def _auto_save_loop(self):
        """Background loop for auto-saving"""
        while self.is_running:
            try:
                await asyncio.sleep(self.AUTO_SAVE_INTERVAL)
                await self.save()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[STATE] Auto-save error: {e}")
    
    # ==================== STATE UPDATES ====================
    
    def update_portfolio(
        self,
        cash: float = None,
        total_trades: int = None,
        winning_trades: int = None,
        losing_trades: int = None
    ):
        """Update portfolio values"""
        if cash is not None:
            self.state.cash = cash
        if total_trades is not None:
            self.state.total_trades = total_trades
        if winning_trades is not None:
            self.state.winning_trades = winning_trades
        if losing_trades is not None:
            self.state.losing_trades = losing_trades
    
    def add_position(self, symbol: str, position_data: Dict):
        """Add or update a position"""
        self.state.positions[symbol] = position_data
    
    def remove_position(self, symbol: str):
        """Remove a position"""
        if symbol in self.state.positions:
            del self.state.positions[symbol]
    
    def add_trade(self, trade_data: Dict):
        """Add a trade to history"""
        self.state.trade_history.append(trade_data)
        self.state.trade_counter += 1
        
        # Keep only last 100 trades
        if len(self.state.trade_history) > 100:
            self.state.trade_history = self.state.trade_history[-100:]
    
    def increment_signals(self):
        """Increment signals processed counter"""
        self.state.signals_processed += 1
    
    # ==================== GETTERS ====================
    
    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value"""
        positions_value = sum(
            pos.get('value', 0) 
            for pos in self.state.positions.values()
        )
        return self.state.cash + positions_value
    
    def get_total_pnl(self) -> float:
        """Get total PnL"""
        return self.get_portfolio_value() - self.state.initial_capital
    
    def get_win_rate(self) -> float:
        """Get win rate percentage"""
        if self.state.total_trades == 0:
            return 0.0
        return (self.state.winning_trades / self.state.total_trades) * 100
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            "initial_capital": self.state.initial_capital,
            "cash": self.state.cash,
            "portfolio_value": self.get_portfolio_value(),
            "total_pnl": self.get_total_pnl(),
            "total_pnl_pct": (self.get_total_pnl() / self.state.initial_capital) * 100,
            "total_trades": self.state.total_trades,
            "winning_trades": self.state.winning_trades,
            "losing_trades": self.state.losing_trades,
            "win_rate": self.get_win_rate(),
            "open_positions": len(self.state.positions),
            "signals_processed": self.state.signals_processed,
            "started_at": self.state.started_at,
            "last_save": self.state.last_save
        }


# Global instance
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create global state manager"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


async def init_state_manager() -> StateManager:
    """Initialize and load state manager"""
    manager = get_state_manager()
    await manager.load()
    await manager.start_auto_save()
    return manager

