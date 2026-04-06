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
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

import pathlib as _pathlib

# Persistent storage: use /data/ (Railway volume) or fallback to /tmp/
_DATA_DIR = _pathlib.Path("/data")
if not _DATA_DIR.exists():
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        _DATA_DIR = _pathlib.Path("/tmp")
STATS_FILE = str(_DATA_DIR / "safety_stats.json")


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
    - 15+ simulation trades completed (full buy→sell cycles)  [was 20]
    - Win rate >= 35%
    - Total PnL > $0

    Auto-stop criteria (back to simulation):
    - Daily loss > $50  [was $30 — allows larger real trades]
    - Real win rate drops below 25% after 10+ real trades

    Progressive trade limit:
    - First 10 real trades: $50 max
    - Trades 11-30: $100 max  (auto-evolved by auto_evolve())
    - After 30 trades: $200 max
    """

    MIN_SIM_TRADES = 15           # was 20 — faster to prove bot works
    MIN_SIM_WIN_RATE = 35.0
    MAX_DAILY_LOSS_USD = 50.0     # was $30 — more room to breathe
    MAX_TRADE_USD = 50.0
    REAL_MIN_WIN_RATE = 25.0
    REAL_MIN_TRADES_FOR_CHECK = 10
    
    CONSECUTIVE_LOSS_LIMIT = 3
    LOSS_COOLDOWN_SECONDS = 1800  # 30 min pause after 3 consecutive losses

    PRICE_CACHE_TTL = 300
    NATIVE_FALLBACK: Dict[str, float] = {"bsc": 660.0, "base": 2100.0}

    def __init__(self):
        self.stats = SafetyStats()
        self.trade_history: List[TradeRecord] = []
        self._notifier = None
        self._consecutive_losses = 0
        self._cooldown_until = 0.0
        self._native_price_cache: Dict[str, Tuple[float, float]] = {}
        self._load_stats()
        self.recalculate_pnl()

    def set_notifier(self, callback):
        """Register an async callback for critical safety events.

        The callback receives (event_type: str, data: dict).
        Event types: 'mode_change', 'emergency_stop', 'emergency_unlock'.
        """
        self._notifier = callback

    def _fire_notifier(self, event_type: str, data: dict):
        """Schedule the notifier callback without blocking."""
        if self._notifier is None:
            return
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self._notifier(event_type, data))
        except RuntimeError:
            pass
        except Exception as e:
            logger.debug(f"[SAFETY] Notifier fire error: {e}")
    
    def _load_stats(self):
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, 'r') as f:
                    data = json.load(f)
                self.stats = SafetyStats(**{k: v for k, v in data.get("stats", {}).items() if k in SafetyStats.__dataclass_fields__})
                for t in data.get("trades", [])[-200:]:
                    self.trade_history.append(TradeRecord(**{k: v for k, v in t.items() if k in TradeRecord.__dataclass_fields__}))
                evolved_trade = data.get("evolved_max_trade_usd")
                if evolved_trade is not None:
                    self.MAX_TRADE_USD = evolved_trade
                evolved_loss = data.get("evolved_max_daily_loss_usd")
                if evolved_loss is not None:
                    self.MAX_DAILY_LOSS_USD = evolved_loss
                logger.info(f"[SAFETY] Loaded stats: {self.stats.sim_trades_total} sim trades, {self.stats.real_trades_total} real trades")
        except Exception as e:
            logger.warning(f"[SAFETY] Could not load stats: {e}")
    
    def _save_stats(self):
        try:
            self.stats.last_updated = datetime.now(timezone.utc).isoformat()
            data = {
                "stats": asdict(self.stats),
                "trades": [asdict(t) for t in self.trade_history[-200:]],
                "evolved_max_trade_usd": self.MAX_TRADE_USD,
                "evolved_max_daily_loss_usd": self.MAX_DAILY_LOSS_USD,
            }
            with open(STATS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[SAFETY] Could not save stats: {e}")
    
    def _reset_daily_if_needed(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
                self._fire_notifier("emergency_unlock", {})
    
    # ==================== PRE-TRADE GATE ====================
    
    def is_in_cooldown(self) -> Tuple[bool, float]:
        """Check if bot is in loss cooldown. Returns (in_cooldown, seconds_remaining)."""
        import time
        now = time.time()
        if now < self._cooldown_until:
            return True, self._cooldown_until - now
        return False, 0
    
    def can_trade_real(self, network: str, amount_usd: float) -> Tuple[bool, str]:
        """
        THE MAIN GATE. Called before EVERY real transaction.
        Returns (allowed, reason).
        If this returns False, the trade MUST NOT execute.
        """
        self._reset_daily_if_needed()
        
        # Consecutive loss cooldown
        in_cooldown, remaining = self.is_in_cooldown()
        if in_cooldown:
            return False, f"LOSS COOLDOWN: {remaining/60:.0f}min remaining after {self.CONSECUTIVE_LOSS_LIMIT} consecutive losses"
        
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
            reason = f"DAILY LOSS LIMIT: ${self.stats.daily_pnl_usd:.2f} (max -${self.MAX_DAILY_LOSS_USD})"
            self._fire_notifier("emergency_stop", {"reason": reason})
            return False, reason
        
        # Real win rate check (after enough real trades)
        if self.stats.real_trades_total >= self.REAL_MIN_TRADES_FOR_CHECK:
            real_wr = (self.stats.real_trades_won / self.stats.real_trades_total) * 100
            if real_wr < self.REAL_MIN_WIN_RATE:
                self.stats.emergency_stop = True
                self._save_stats()
                reason = f"Real win rate too low: {real_wr:.1f}% < {self.REAL_MIN_WIN_RATE}%"
                self._fire_notifier("emergency_stop", {"reason": reason})
                return False, reason
        
        # Trade amount sanity
        if amount_usd > self.MAX_TRADE_USD:
            return False, f"Trade ${amount_usd:.2f} > ${self.MAX_TRADE_USD} max"
        
        return True, "All safety checks passed"
    
    MIN_WALLET_USD_FOR_REAL = 30.0

    async def _get_native_price(self, network: str) -> float:
        import time
        symbol_map = {"bsc": "BNBUSDT", "base": "ETHUSDT"}
        symbol = symbol_map.get(network)
        if not symbol:
            return self.NATIVE_FALLBACK.get(network, 0.0)

        cached = self._native_price_cache.get(network)
        if cached and (time.time() - cached[1]) < self.PRICE_CACHE_TTL:
            return cached[0]

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data["price"])
                        self._native_price_cache[network] = (price, time.time())
                        return price
        except Exception as e:
            logger.debug(f"[SAFETY] Binance price fetch failed for {network}: {e}")

        if cached:
            return cached[0]
        return self.NATIVE_FALLBACK.get(network, 0.0)

    def _get_cached_native_price(self, network: str) -> float:
        import time
        cached = self._native_price_cache.get(network)
        if cached and (time.time() - cached[1]) < self.PRICE_CACHE_TTL:
            return cached[0]
        if cached:
            return cached[0]
        return self.NATIVE_FALLBACK.get(network, 0.0)

    def _get_wallet_balance_usd(self) -> float:
        try:
            from web3 import Web3
            from src.core.config import settings
            pk = settings.WALLET_PRIVATE_KEY
            if not pk:
                return 0.0
            if not pk.startswith("0x"):
                pk = "0x" + pk
            addr = Web3().eth.account.from_key(pk).address

            total = 0.0
            rpcs = {
                "bsc": getattr(settings, "BSC_RPC_URL", None),
                "base": getattr(settings, "BASE_RPC_URL", None),
            }
            for net, rpc in rpcs.items():
                if not rpc:
                    continue
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
                    bal = w3.eth.get_balance(addr) / 1e18
                    native_usd = self._get_cached_native_price(net)
                    total += bal * native_usd
                except Exception:
                    pass
            return total
        except Exception:
            return 0.0

    def is_simulation_mode(self) -> bool:
        """
        AUTOMATIC mode detection:
        - Starts in simulation
        - Auto-switches to real when sim criteria are met
        - Auto-reverts to simulation on emergency stop
        - Stays in simulation if wallet balance too low
        """
        sim_env = os.getenv("SIMULATION_MODE", "true").lower()
        if sim_env in ("false", "0", "no", "off"):
            return False
        
        if self.stats.emergency_stop:
            return True
        
        if self.stats.real_trading_unlocked and self.stats.auto_switched_to_real:
            wallet_usd = self._get_wallet_balance_usd()
            if wallet_usd < self.MIN_WALLET_USD_FOR_REAL:
                logger.info(f"[SAFETY] Unlocked but wallet ${wallet_usd:.2f} < ${self.MIN_WALLET_USD_FOR_REAL} — staying in SIMULATION")
                return True
            return False
        
        return True
    
    # ==================== TRADE RECORDING ====================
    
    def record_buy(self, token: str, network: str, amount_usd: float, price: float, is_sim: bool):
        record = TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
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
        
        try:
            from src.data.storage.trade_recorder import record_trade, fire_and_forget
            fire_and_forget(record_trade(
                strategy="sniper", side="BUY", symbol=token, chain=network,
                amount_usd=amount_usd, price=price, is_simulation=is_sim,
            ))
        except Exception:
            pass
    
    def record_sell(self, token: str, network: str, amount_usd: float,
                    pnl_pct: float = 0.0, pnl_usd: float = 0.0, is_sim: bool = True,
                    buy_price: float = 0.0, sell_price: float = 0.0):
        if pnl_usd == 0.0 and buy_price > 0 and sell_price > 0:
            pnl_pct = ((sell_price - buy_price) / buy_price) * 100
            pnl_usd = amount_usd * (pnl_pct / 100)

        record = TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            token=token, network=network, action="sell",
            amount_usd=amount_usd, price=sell_price,
            is_simulation=is_sim, pnl_percent=pnl_pct, pnl_usd=pnl_usd,
        )
        self.trade_history.append(record)
        
        won = pnl_pct > 0
        is_grid = token.startswith("GRID_")
        
        # Track consecutive losses for cooldown
        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.CONSECUTIVE_LOSS_LIMIT:
                import time
                self._cooldown_until = time.time() + self.LOSS_COOLDOWN_SECONDS
                logger.warning(f"[SAFETY] ⏸️ {self._consecutive_losses} consecutive losses — "
                               f"COOLDOWN {self.LOSS_COOLDOWN_SECONDS/60:.0f}min activated")
                self._fire_notifier("loss_cooldown", {
                    "consecutive_losses": self._consecutive_losses,
                    "cooldown_minutes": self.LOSS_COOLDOWN_SECONDS / 60
                })
        
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

            # Track real profit for humanitarian mission
            if pnl_usd > 0:
                try:
                    from src.modules.charity_tracker import get_charity_tracker
                    strategy = "grid" if is_grid else "momentum"
                    get_charity_tracker().record_trade(
                        pnl_usd=pnl_usd, symbol=token,
                        strategy=strategy, is_simulation=False
                    )
                except Exception:
                    pass
        
        self._check_unlock_status()
        self._save_stats()
        
        try:
            from src.data.storage.trade_recorder import record_trade, fire_and_forget
            strategy = "grid" if is_grid else "momentum"
            fire_and_forget(record_trade(
                strategy=strategy, side="SELL", symbol=token, chain=network,
                amount_usd=amount_usd, price=sell_price, status="SUCCESS",
                pnl_usd=pnl_usd, pnl_pct=pnl_pct, is_simulation=is_sim,
            ))
        except Exception:
            pass
    
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

        logger.info(
            f"[SAFETY] Unlock check: trades={self.stats.sim_trades_total}/{self.MIN_SIM_TRADES} "
            f"WR={self.stats.sim_win_rate:.1f}%/{self.MIN_SIM_WIN_RATE}% "
            f"PnL=${self.stats.sim_total_pnl_usd:+.2f}(need>$0) | "
            f"Grid:{self.stats.grid_trades_total}t/{self.MIN_GRID_TRADES_FOR_UNLOCK} "
            f"GWR={grid_wr:.0f}%/{self.MIN_GRID_WIN_RATE}% "
            f"MomWR={mom_wr:.0f}%/20% | "
            f"overall={overall_criteria} grid_path={grid_criteria} => {'UNLOCK' if criteria_met else 'LOCKED'}"
        )

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
                self._fire_notifier("mode_change", {
                    "old_mode": "SIMULATION",
                    "new_mode": "REAL",
                    "reason": self.stats.unlock_reason,
                })
        else:
            remaining = max(0, self.MIN_SIM_TRADES - self.stats.sim_trades_total)
            self.stats.unlock_reason = (
                f"Need {remaining} more trades, WR {self.stats.sim_win_rate:.1f}%/{self.MIN_SIM_WIN_RATE}%, "
                f"PnL ${self.stats.sim_total_pnl_usd:+.2f} (must be >$0), "
                f"Mom WR {mom_wr:.0f}% (need >=20%)"
            )
            if was_unlocked:
                self._fire_notifier("mode_change", {
                    "old_mode": "REAL",
                    "new_mode": "SIMULATION",
                    "reason": self.stats.unlock_reason,
                })
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
    
    def recalculate_pnl(self):
        """Recalculate PnL from trade history, capping losses at -20% to fix past -100% bugs."""
        MAX_LOSS_CAP_PCT = -20.0
        sim_pnl = 0.0
        grid_pnl = 0.0
        mom_pnl = 0.0
        sim_total = 0
        sim_won = 0
        sim_lost = 0
        grid_total = 0
        grid_won = 0
        mom_total = 0
        mom_won = 0

        for t in self.trade_history:
            if t.action != "sell" or not t.is_simulation:
                continue
            capped_pct = max(t.pnl_percent, MAX_LOSS_CAP_PCT)
            capped_usd = t.amount_usd * (capped_pct / 100) if t.amount_usd > 0 else t.pnl_usd
            if capped_pct != t.pnl_percent:
                logger.info(f"[SAFETY] Recalc: {t.token} capped {t.pnl_percent:+.1f}% → {capped_pct:+.1f}%")

            sim_total += 1
            won = capped_pct > 0
            if won:
                sim_won += 1
            else:
                sim_lost += 1
            sim_pnl += capped_usd

            is_grid = t.token.startswith("GRID_")
            if is_grid:
                grid_total += 1
                if won:
                    grid_won += 1
                grid_pnl += capped_usd
            else:
                mom_total += 1
                if won:
                    mom_won += 1
                mom_pnl += capped_usd

        self.stats.sim_trades_total = sim_total
        self.stats.sim_trades_won = sim_won
        self.stats.sim_trades_lost = sim_lost
        self.stats.sim_total_pnl_usd = sim_pnl
        self.stats.grid_trades_total = grid_total
        self.stats.grid_trades_won = grid_won
        self.stats.grid_total_pnl_usd = grid_pnl
        self.stats.momentum_trades_total = mom_total
        self.stats.momentum_trades_won = mom_won
        self.stats.momentum_total_pnl_usd = mom_pnl
        self._recalc_sim_stats()
        self._check_unlock_status()
        self._save_stats()
        logger.info(f"[SAFETY] PnL recalculated: {sim_total}t WR={self.stats.sim_win_rate:.1f}% PnL=${sim_pnl:+.2f}")

    def auto_evolve(self) -> Dict:
        """Analyze trade history and auto-adjust parameters for continuous improvement."""
        sells = [t for t in self.trade_history if t.action == "sell"]
        if len(sells) < 10:
            return {"evolved": False, "reason": f"Not enough trades ({len(sells)}/10)"}

        wins = [t for t in sells if t.pnl_percent > 0]
        losses = [t for t in sells if t.pnl_percent <= 0]
        changes = {}

        avg_win = sum(t.pnl_percent for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_percent for t in losses) / len(losses) if losses else 0
        win_rate = len(wins) / len(sells) * 100

        old_max_trade = self.MAX_TRADE_USD
        old_daily_loss = self.MAX_DAILY_LOSS_USD

        # Progressive scaling: more aggressive limit increases as confidence grows
        # Cap scales with number of real trades to limit risk on early real trading
        real_trades = self.stats.real_trades_total
        if real_trades < 10:
            progressive_cap = 100.0
        elif real_trades < 30:
            progressive_cap = 200.0
        elif real_trades < 60:
            progressive_cap = 500.0
        else:
            progressive_cap = 1000.0

        if win_rate >= 60 and avg_win > abs(avg_loss):
            new_max_trade = min(old_max_trade * 1.20, progressive_cap)
            if new_max_trade > old_max_trade:
                self.MAX_TRADE_USD = round(new_max_trade, 2)
                changes["max_trade_usd"] = f"${old_max_trade} → ${self.MAX_TRADE_USD} (cap: ${progressive_cap})"
        elif win_rate < 45 or avg_win < abs(avg_loss) * 0.5:
            new_max_trade = max(old_max_trade * 0.8, 20.0)
            if new_max_trade != old_max_trade:
                self.MAX_TRADE_USD = round(new_max_trade, 2)
                changes["max_trade_usd"] = f"${old_max_trade} → ${self.MAX_TRADE_USD}"

        big_losses = [t for t in losses if t.pnl_percent < -25]
        if len(big_losses) > len(sells) * 0.15:
            changes["stop_loss_tighten"] = f"{len(big_losses)} trades > -25% loss — tightening recommended"

        recent = sells[-15:]
        recent_wr = len([t for t in recent if t.pnl_percent > 0]) / len(recent) * 100
        recent_pnl = sum(t.pnl_usd for t in recent)
        if recent_wr < 40 and recent_pnl < -5:
            new_daily_loss = max(old_daily_loss * 0.85, 15.0)
            if new_daily_loss != old_daily_loss:
                self.MAX_DAILY_LOSS_USD = round(new_daily_loss, 2)
                changes["daily_loss_limit"] = f"${old_daily_loss} → ${self.MAX_DAILY_LOSS_USD}"

        if recent_wr >= 65 and recent_pnl > 0:
            new_daily_loss = min(old_daily_loss * 1.1, 100.0)
            if new_daily_loss != old_daily_loss:
                self.MAX_DAILY_LOSS_USD = round(new_daily_loss, 2)
                changes["daily_loss_limit"] = f"${old_daily_loss} → ${self.MAX_DAILY_LOSS_USD}"

        if changes:
            self._save_stats()
            logger.info(f"[EVOLVE] Auto-evolution applied: {changes}")
            self._fire_notifier("regime_change", {
                "old_regime": "previous_params",
                "new_regime": f"evolved ({len(changes)} changes)",
            })

        return {
            "evolved": bool(changes),
            "changes": changes,
            "stats": {
                "total_trades": len(sells),
                "win_rate": f"{win_rate:.1f}%",
                "avg_win": f"+{avg_win:.1f}%",
                "avg_loss": f"{avg_loss:.1f}%",
                "recent_15_wr": f"{recent_wr:.1f}%",
                "recent_15_pnl": f"${recent_pnl:+.2f}",
            },
            "params": {
                "max_trade_usd": self.MAX_TRADE_USD,
                "daily_loss_limit": self.MAX_DAILY_LOSS_USD,
            }
        }

    def reset_simulation(self):
        """Reset simulation stats to start fresh (e.g. after strategy change)"""
        logger.info("[SAFETY] Resetting simulation stats for new strategy test")
        self.stats = SafetyStats()
        self.trade_history.clear()
        self._consecutive_losses = 0
        self._cooldown_until = 0.0
        self._save_stats()
        logger.info("[SAFETY] Simulation reset complete - starting from 0/20 trades")


# Singleton
_safety_manager: Optional[SafetyManager] = None

def get_safety_manager() -> SafetyManager:
    global _safety_manager
    if _safety_manager is None:
        _safety_manager = SafetyManager()
    return _safety_manager
