"""
Safety Manager - FULLY AUTOMATIC mode switching.

HOW IT WORKS:
1. Bot starts in SIMULATION (no real money spent)
2. Bot runs simulated trades, tracks every result
3. After 20 completed sim trades with win rate >= 35%:
   → Bot AUTOMATICALLY switches to REAL trading
4. In real mode, daily loss limit ($30) auto-stops and reverts to simulation
5. If win rate drops below 25% in real mode → back to simulation

NO MANUAL INTERVENTION NEEDED. The bot proves itself before spending money.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

STATS_FILE = "/tmp/safety_stats.json"


@dataclass
class TradeRecord:
    timestamp: str
    token: str
    network: str
    action: str  # "buy" or "sell"
    amount_usd: float
    price: float
    is_simulation: bool
    pnl_percent: float = 0.0
    pnl_usd: float = 0.0


@dataclass
class SafetyStats:
    sim_trades_total: int = 0
    sim_trades_won: int = 0
    sim_trades_lost: int = 0
    sim_win_rate: float = 0.0
    sim_avg_win_pct: float = 0.0
    sim_avg_loss_pct: float = 0.0
    sim_total_pnl_usd: float = 0.0
    
    # Separate tracking: grid vs momentum
    grid_trades_total: int = 0
    grid_trades_won: int = 0
    grid_total_pnl_usd: float = 0.0
    momentum_trades_total: int = 0
    momentum_trades_won: int = 0
    momentum_total_pnl_usd: float = 0.0
    
    real_trades_total: int = 0
    real_trades_won: int = 0
    real_trades_lost: int = 0
    real_total_pnl_usd: float = 0.0
    
    daily_pnl_usd: float = 0.0
    daily_trades: int = 0
    daily_reset_date: str = ""
    
    real_trading_unlocked: bool = False
    unlock_reason: str = ""
    auto_switched_to_real: bool = False
    emergency_stop: bool = False
    last_updated: str = ""


class SafetyManager:
    """
    FULLY AUTOMATIC safety system.
    
    Auto-unlock criteria:
    - 20+ simulation trades completed (full buy→sell cycles)
    - Win rate >= 35%
    
    Auto-stop criteria (back to simulation):
    - Daily loss > $30
    - Real win rate drops below 25% after 10+ real trades
    """
    
    MIN_SIM_TRADES = 20
    MIN_SIM_WIN_RATE = 35.0
    MAX_DAILY_LOSS_USD = 30.0
    MAX_TRADE_USD = 50.0
    REAL_MIN_WIN_RATE = 25.0
    REAL_MIN_TRADES_FOR_CHECK = 10
    
    def __init__(self):
        self.stats = SafetyStats()
        self.trade_history: List[TradeRecord] = []
        self._load_stats()
    
    def _load_stats(self):
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, 'r') as f:
                    data = json.load(f)
                self.stats = SafetyStats(**{k: v for k, v in data.get("stats", {}).items() if k in SafetyStats.__dataclass_fields__})
                for t in data.get("trades", [])[-200:]:
                    self.trade_history.append(TradeRecord(**{k: v for k, v in t.items() if k in TradeRecord.__dataclass_fields__}))
                logger.info(f"[SAFETY] Loaded stats: {self.stats.sim_trades_total} sim trades, {self.stats.real_trades_total} real trades")
        except Exception as e:
            logger.warning(f"[SAFETY] Could not load stats: {e}")
    
    def _save_stats(self):
        try:
            self.stats.last_updated = datetime.utcnow().isoformat()
            data = {
                "stats": asdict(self.stats),
                "trades": [asdict(t) for t in self.trade_history[-200:]]
            }
            with open(STATS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[SAFETY] Could not save stats: {e}")
    
    def _reset_daily_if_needed(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self.stats.daily_reset_date != today:
            if self.stats.daily_pnl_usd != 0:
                logger.info(f"[SAFETY] Daily reset: yesterday P&L was ${self.stats.daily_pnl_usd:.2f}")
            self.stats.daily_pnl_usd = 0.0
            self.stats.daily_trades = 0
            self.stats.daily_reset_date = today
            
            if self.stats.emergency_stop:
                logger.info("[SAFETY] Emergency stop cleared after daily reset - re-entering simulation")
                self.stats.emergency_stop = False
                self.stats.auto_switched_to_real = False
                self.stats.real_trading_unlocked = False
                self._save_stats()
    
    # ==================== PRE-TRADE GATE ====================
    
    def can_trade_real(self, network: str, amount_usd: float) -> Tuple[bool, str]:
        """
        THE MAIN GATE. Called before EVERY real transaction.
        Returns (allowed, reason).
        If this returns False, the trade MUST NOT execute.
        """
        self._reset_daily_if_needed()
        
        # Emergency stop
        if self.stats.emergency_stop:
            return False, "EMERGENCY STOP active - bot paused"
        
        # Must have proven in simulation first
        if self.stats.sim_trades_total < self.MIN_SIM_TRADES:
            return False, f"Need {self.MIN_SIM_TRADES} sim trades, have {self.stats.sim_trades_total}"
        
        if self.stats.sim_win_rate < self.MIN_SIM_WIN_RATE:
            return False, f"Sim win rate {self.stats.sim_win_rate:.1f}% < {self.MIN_SIM_WIN_RATE}%"
        
        # Daily loss protection
        if self.stats.daily_pnl_usd < -self.MAX_DAILY_LOSS_USD:
            self.stats.emergency_stop = True
            self._save_stats()
            return False, f"DAILY LOSS LIMIT: ${self.stats.daily_pnl_usd:.2f} (max -${self.MAX_DAILY_LOSS_USD})"
        
        # Real win rate check (after enough real trades)
        if self.stats.real_trades_total >= self.REAL_MIN_TRADES_FOR_CHECK:
            real_wr = (self.stats.real_trades_won / self.stats.real_trades_total) * 100
            if real_wr < self.REAL_MIN_WIN_RATE:
                self.stats.emergency_stop = True
                self._save_stats()
                return False, f"Real win rate too low: {real_wr:.1f}% < {self.REAL_MIN_WIN_RATE}%"
        
        # Trade amount sanity
        if amount_usd > self.MAX_TRADE_USD:
            return False, f"Trade ${amount_usd:.2f} > ${self.MAX_TRADE_USD} max"
        
        return True, "All safety checks passed"
    
    def is_simulation_mode(self) -> bool:
        """
        AUTOMATIC mode detection:
        - Starts in simulation
        - Auto-switches to real when sim criteria are met
        - Auto-reverts to simulation on emergency stop
        """
        # Hard override: SIMULATION_MODE=false in env = force real (skip sim validation)
        sim_env = os.getenv("SIMULATION_MODE", "true").lower()
        if sim_env in ("false", "0", "no", "off"):
            return False
        
        # Emergency stop = back to simulation
        if self.stats.emergency_stop:
            return True
        
        # Auto-switch: sim criteria met = go real
        if self.stats.real_trading_unlocked and self.stats.auto_switched_to_real:
            return False
        
        # Default: simulation
        return True
    
    # ==================== TRADE RECORDING ====================
    
    def record_buy(self, token: str, network: str, amount_usd: float, price: float, is_sim: bool):
        record = TradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            token=token,
            network=network,
            action="buy",
            amount_usd=amount_usd,
            price=price,
            is_simulation=is_sim,
        )
        self.trade_history.append(record)
        
        if is_sim:
            logger.info(f"[SAFETY] SIM buy recorded: {token} ${amount_usd:.2f}")
        else:
            self.stats.daily_trades += 1
            logger.info(f"[SAFETY] REAL buy recorded: {token} ${amount_usd:.2f}")
        
        self._save_stats()
    
    def record_sell(self, token: str, network: str, amount_usd: float,
                    pnl_pct: float = 0.0, pnl_usd: float = 0.0, is_sim: bool = True,
                    buy_price: float = 0.0, sell_price: float = 0.0):
        if pnl_usd == 0.0 and buy_price > 0 and sell_price > 0:
            pnl_pct = ((sell_price - buy_price) / buy_price) * 100
            pnl_usd = amount_usd * (pnl_pct / 100)

        record = TradeRecord(
            timestamp=datetime.utcnow().isoformat(),
            token=token, network=network, action="sell",
            amount_usd=amount_usd, price=sell_price,
            is_simulation=is_sim, pnl_percent=pnl_pct, pnl_usd=pnl_usd,
        )
        self.trade_history.append(record)
        
        won = pnl_pct > 0
        is_grid = token.startswith("GRID_")
        
        if is_sim:
            self.stats.sim_trades_total += 1
            if won:
                self.stats.sim_trades_won += 1
            else:
                self.stats.sim_trades_lost += 1
            self.stats.sim_total_pnl_usd += pnl_usd
            
            if is_grid:
                self.stats.grid_trades_total += 1
                if won:
                    self.stats.grid_trades_won += 1
                self.stats.grid_total_pnl_usd += pnl_usd
            else:
                self.stats.momentum_trades_total += 1
                if won:
                    self.stats.momentum_trades_won += 1
                self.stats.momentum_total_pnl_usd += pnl_usd
            
            self._recalc_sim_stats()
            grid_wr = (self.stats.grid_trades_won / max(self.stats.grid_trades_total, 1)) * 100
            mom_wr = (self.stats.momentum_trades_won / max(self.stats.momentum_trades_total, 1)) * 100
            logger.info(f"[SAFETY] SIM sell: {token} PnL {pnl_pct:+.1f}% (${pnl_usd:+.2f}) | "
                        f"Overall: {self.stats.sim_win_rate:.1f}% ({self.stats.sim_trades_total}t) | "
                        f"Grid: {grid_wr:.0f}% ({self.stats.grid_trades_total}t) | Mom: {mom_wr:.0f}% ({self.stats.momentum_trades_total}t)")
        else:
            self.stats.real_trades_total += 1
            if won:
                self.stats.real_trades_won += 1
            else:
                self.stats.real_trades_lost += 1
            self.stats.real_total_pnl_usd += pnl_usd
            self.stats.daily_pnl_usd += pnl_usd
            logger.info(f"[SAFETY] REAL sell: {token} PnL {pnl_pct:+.1f}% (${pnl_usd:+.2f}) | Daily: ${self.stats.daily_pnl_usd:+.2f}")
        
        self._check_unlock_status()
        self._save_stats()
    
    def _recalc_sim_stats(self):
        if self.stats.sim_trades_total > 0:
            self.stats.sim_win_rate = (self.stats.sim_trades_won / self.stats.sim_trades_total) * 100
        
        wins = [t.pnl_percent for t in self.trade_history if t.is_simulation and t.action == "sell" and t.pnl_percent > 0]
        losses = [t.pnl_percent for t in self.trade_history if t.is_simulation and t.action == "sell" and t.pnl_percent <= 0]
        
        self.stats.sim_avg_win_pct = sum(wins) / len(wins) if wins else 0
        self.stats.sim_avg_loss_pct = sum(losses) / len(losses) if losses else 0
    
    MIN_GRID_TRADES_FOR_UNLOCK = 10
    MIN_GRID_WIN_RATE = 50.0
    
    def _check_unlock_status(self):
        was_unlocked = self.stats.real_trading_unlocked

        if self.stats.emergency_stop:
            self.stats.real_trading_unlocked = False
            self.stats.auto_switched_to_real = False
            self.stats.unlock_reason = "EMERGENCY STOP - reverted to simulation"
            return

        # STRICT unlock: require BOTH overall performance AND positive PnL
        overall_criteria = (
            self.stats.sim_trades_total >= self.MIN_SIM_TRADES and
            self.stats.sim_win_rate >= self.MIN_SIM_WIN_RATE and
            self.stats.sim_total_pnl_usd > 0
        )

        # Grid-only shortcut: grid must be profitable AND momentum must not be
        # actively losing (if momentum has trades, its WR must be >= 20%)
        grid_wr = (self.stats.grid_trades_won / max(self.stats.grid_trades_total, 1)) * 100
        mom_wr = (self.stats.momentum_trades_won / max(self.stats.momentum_trades_total, 1)) * 100
        momentum_ok = (self.stats.momentum_trades_total == 0 or mom_wr >= 20.0)
        grid_criteria = (
            self.stats.grid_trades_total >= self.MIN_GRID_TRADES_FOR_UNLOCK and
            grid_wr >= self.MIN_GRID_WIN_RATE and
            self.stats.grid_total_pnl_usd > 0 and
            momentum_ok
        )

        criteria_met = grid_criteria or overall_criteria

        if criteria_met:
            self.stats.real_trading_unlocked = True
            self.stats.unlock_reason = (
                f"AUTO-UNLOCKED: {self.stats.sim_trades_total} trades, "
                f"{self.stats.sim_win_rate:.1f}% WR, "
                f"PnL ${self.stats.sim_total_pnl_usd:+.2f}, "
                f"Grid {grid_wr:.0f}%/{self.stats.grid_trades_total}t, "
                f"Mom {mom_wr:.0f}%/{self.stats.momentum_trades_total}t"
            )
            if not was_unlocked:
                self.stats.auto_switched_to_real = True
                logger.info("=" * 60)
                logger.info(f"[SAFETY] *** AUTO-SWITCH TO REAL TRADING ***")
                logger.info(f"[SAFETY] {self.stats.unlock_reason}")
                logger.info(f"[SAFETY] Daily loss limit: ${self.MAX_DAILY_LOSS_USD}")
                logger.info("=" * 60)
        else:
            remaining = max(0, self.MIN_SIM_TRADES - self.stats.sim_trades_total)
            self.stats.unlock_reason = (
                f"Need {remaining} more trades, WR {self.stats.sim_win_rate:.1f}%/{self.MIN_SIM_WIN_RATE}%, "
                f"PnL ${self.stats.sim_total_pnl_usd:+.2f} (must be >$0), "
                f"Mom WR {mom_wr:.0f}% (need >=20%)"
            )
            self.stats.real_trading_unlocked = False
    
    # ==================== STATUS & REPORTING ====================
    
    def get_status(self) -> Dict:
        self._reset_daily_if_needed()
        self._check_unlock_status()
        grid_wr = (self.stats.grid_trades_won / max(self.stats.grid_trades_total, 1)) * 100
        mom_wr = (self.stats.momentum_trades_won / max(self.stats.momentum_trades_total, 1)) * 100
        return {
            "simulation": {
                "trades": self.stats.sim_trades_total,
                "won": self.stats.sim_trades_won,
                "lost": self.stats.sim_trades_lost,
                "win_rate": f"{self.stats.sim_win_rate:.1f}%",
                "avg_win": f"+{self.stats.sim_avg_win_pct:.1f}%",
                "avg_loss": f"{self.stats.sim_avg_loss_pct:.1f}%",
                "total_pnl": f"${self.stats.sim_total_pnl_usd:+.2f}",
                "needed_for_unlock": max(0, self.MIN_SIM_TRADES - self.stats.sim_trades_total),
            },
            "grid": {
                "trades": self.stats.grid_trades_total,
                "won": self.stats.grid_trades_won,
                "win_rate": f"{grid_wr:.1f}%",
                "pnl": f"${self.stats.grid_total_pnl_usd:+.2f}",
                "unlock_at": f"{self.MIN_GRID_TRADES_FOR_UNLOCK} trades @ {self.MIN_GRID_WIN_RATE}% WR",
            },
            "momentum": {
                "trades": self.stats.momentum_trades_total,
                "won": self.stats.momentum_trades_won,
                "win_rate": f"{mom_wr:.1f}%",
                "pnl": f"${self.stats.momentum_total_pnl_usd:+.2f}",
            },
            "real": {
                "trades": self.stats.real_trades_total,
                "won": self.stats.real_trades_won,
                "lost": self.stats.real_trades_lost,
                "total_pnl": f"${self.stats.real_total_pnl_usd:+.2f}",
                "daily_pnl": f"${self.stats.daily_pnl_usd:+.2f}",
                "daily_trades": self.stats.daily_trades,
            },
            "safety": {
                "current_mode": "REAL" if not self.is_simulation_mode() else "SIMULATION",
                "auto_switch_enabled": True,
                "real_trading_unlocked": self.stats.real_trading_unlocked,
                "auto_switched_to_real": self.stats.auto_switched_to_real,
                "emergency_stop": self.stats.emergency_stop,
                "unlock_reason": self.stats.unlock_reason,
                "daily_loss_limit": f"${self.MAX_DAILY_LOSS_USD}",
                "max_trade_usd": self.MAX_TRADE_USD,
            }
        }
    
    def get_progress_bar(self) -> str:
        done = min(self.stats.sim_trades_total, self.MIN_SIM_TRADES)
        total = self.MIN_SIM_TRADES
        pct = (done / total) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        return f"[{bar}] {done}/{total} trades ({pct:.0f}%) | WR: {self.stats.sim_win_rate:.1f}%"
    
    def reset_simulation(self):
        """Reset simulation stats to start fresh (e.g. after strategy change)"""
        logger.info("[SAFETY] Resetting simulation stats for new strategy test")
        self.stats = SafetyStats()
        self.trade_history.clear()
        self._save_stats()
        logger.info("[SAFETY] Simulation reset complete - starting from 0/20 trades")


# Singleton
_safety_manager: Optional[SafetyManager] = None

def get_safety_manager() -> SafetyManager:
    global _safety_manager
    if _safety_manager is None:
        _safety_manager = SafetyManager()
    return _safety_manager
