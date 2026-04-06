"""
Charity Tracker - Association Netero

Suit l'intégralité des profits générés par le bot pour l'Association Netero.
100% des gains vont directement à l'association via le wallet configuré.

Architecture :
- Chaque trade rentable est enregistré avec son profit
- 100% des profits sont pour l'Association Netero
- Tableau de bord dédié dans le dashboard
- Notifications Telegram pour chaque jalon atteint
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import logging
logger = logging.getLogger(__name__)

# Répertoire de persistance (Railway volume ou /tmp fallback)
_DATA_DIR = "/data" if os.path.isdir("/data") else "/tmp"
_CHARITY_FILE = os.path.join(_DATA_DIR, "charity_stats.json")

# 100% des profits vont à l'Association Netero
CHARITY_RATE = 1.0
ASSOCIATION_NAME = "Association Netero"
ASSOCIATION_EMOJI = "🌍"

# Jalons de notification (en USD de profits pour l'association)
CHARITY_MILESTONES = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]


@dataclass
class CharityStats:
    # Totaux cumulés (100% des profits = pour Netero)
    total_profit_sim_usd: float = 0.0       # Profits en simulation
    total_profit_real_usd: float = 0.0      # Profits réels (= argent réel pour Netero)
    total_trades_profitable: int = 0
    total_trades_total: int = 0

    # Progression
    last_milestone_reached: float = 0.0
    next_milestone: float = 10.0

    # Historique des trades
    contributions: List[Dict] = None

    # Métadonnées
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        if self.contributions is None:
            self.contributions = []
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def total_all_usd(self) -> float:
        return self.total_profit_sim_usd + self.total_profit_real_usd


class CharityTracker:
    """
    Suit tous les profits du bot pour l'Association Netero.

    100% des gains = argent pour l'association.
    En simulation : profits virtuels (preuve que le bot fonctionne).
    En mode réel : profits réels directement dans le wallet de l'association.
    """

    _instance: Optional["CharityTracker"] = None

    def __init__(self):
        self.stats = CharityStats()
        self._notifier = None
        self._load()

    @classmethod
    def get_instance(cls) -> "CharityTracker":
        if cls._instance is None:
            cls._instance = CharityTracker()
        return cls._instance

    def set_notifier(self, callback):
        """Enregistre un callback async pour les jalons."""
        self._notifier = callback

    def record_trade(
        self,
        pnl_usd: float,
        symbol: str,
        strategy: str = "momentum",
        is_simulation: bool = True,
    ) -> Optional[float]:
        """
        Enregistre un trade. Si positif, comptabilise pour l'Association Netero.

        Returns:
            profit_usd si positif, None sinon.
        """
        self.stats.total_trades_total += 1

        if pnl_usd <= 0:
            self._save()
            return None

        # 100% des profits vont à Netero
        if is_simulation:
            self.stats.total_profit_sim_usd = round(self.stats.total_profit_sim_usd + pnl_usd, 4)
        else:
            self.stats.total_profit_real_usd = round(self.stats.total_profit_real_usd + pnl_usd, 4)

        self.stats.total_trades_profitable += 1

        # Log contribution
        contribution = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "strategy": strategy,
            "pnl_usd": round(pnl_usd, 4),
            "is_simulation": is_simulation,
        }
        self.stats.contributions.append(contribution)
        self.stats.contributions = self.stats.contributions[-100:]

        # Check milestone (basé sur les profits réels)
        self._check_milestone(is_simulation)
        self._save()

        mode_label = "(sim)" if is_simulation else "(REEL)"
        logger.info(
            f"[NETERO] +${pnl_usd:.4f} {mode_label} | "
            f"Total réel: ${self.stats.total_profit_real_usd:.2f} | "
            f"Total sim: ${self.stats.total_profit_sim_usd:.2f}"
        )

        return pnl_usd

    def _check_milestone(self, is_simulation: bool):
        """Vérifie si un jalon est franchi (sur profits réels uniquement)."""
        if is_simulation:
            return  # Les jalons ne comptent qu'en mode réel
        total_real = self.stats.total_profit_real_usd
        for milestone in sorted(CHARITY_MILESTONES):
            if total_real >= milestone > self.stats.last_milestone_reached:
                self.stats.last_milestone_reached = milestone
                logger.info(f"[NETERO] JALON ATTEINT: ${milestone} de profits réels pour l'Association Netero!")
                if self._notifier:
                    try:
                        import asyncio
                        asyncio.get_running_loop().create_task(
                            self._notifier("milestone", {"amount": milestone, "total": total_real})
                        )
                    except RuntimeError:
                        pass

        remaining = [m for m in CHARITY_MILESTONES if m > self.stats.last_milestone_reached]
        self.stats.next_milestone = remaining[0] if remaining else CHARITY_MILESTONES[-1]

    def get_stats(self) -> Dict:
        """Retourne les statistiques pour le dashboard."""
        total_real = self.stats.total_profit_real_usd
        next_m = self.stats.next_milestone
        last_m = self.stats.last_milestone_reached

        if next_m > last_m:
            progress_pct = min(100.0, ((total_real - last_m) / (next_m - last_m)) * 100)
        else:
            progress_pct = 100.0 if total_real >= last_m else 0.0

        return {
            "association_name": ASSOCIATION_NAME,
            "total_profit_sim_usd": self.stats.total_profit_sim_usd,
            "total_profit_real_usd": self.stats.total_profit_real_usd,
            "total_profit_usd": self.stats.total_all_usd,  # compat
            "total_charity_usd": self.stats.total_all_usd,  # compat dashboard
            "charity_rate_pct": 100,
            "total_trades": self.stats.total_trades_total,
            "profitable_trades": self.stats.total_trades_profitable,
            "win_rate": (
                (self.stats.total_trades_profitable / self.stats.total_trades_total * 100)
                if self.stats.total_trades_total > 0 else 0.0
            ),
            "last_milestone": self.stats.last_milestone_reached,
            "next_milestone": next_m,
            "progress_to_next_milestone_pct": progress_pct,
            "is_simulation": self.stats.total_profit_real_usd == 0,
            "recent_contributions": self.stats.contributions[-10:],
            "last_updated": self.stats.last_updated,
        }

    def get_impact_message(self) -> str:
        """Message de contexte pour l'Association Netero."""
        real = self.stats.total_profit_real_usd
        sim = self.stats.total_profit_sim_usd
        if real <= 0 and sim <= 0:
            return "Le bot accumule des profits pour l'Association Netero"
        if real <= 0:
            return f"${sim:.2f} générés en simulation — prêt pour le mode réel"
        if real < 50:
            return f"${real:.2f} réels générés pour l'Association Netero"
        if real < 250:
            return f"${real:.2f} — impact croissant pour l'Association Netero"
        return f"${real:.2f} — contribution significative pour l'Association Netero!"

    def _save(self):
        self.stats.last_updated = datetime.now(timezone.utc).isoformat()
        try:
            with open(_CHARITY_FILE, "w") as f:
                json.dump(asdict(self.stats), f, indent=2)
        except Exception as e:
            logger.warning(f"[NETERO] Could not save stats: {e}")

    def _load(self):
        try:
            if os.path.exists(_CHARITY_FILE):
                with open(_CHARITY_FILE) as f:
                    data = json.load(f)
                fields = CharityStats.__dataclass_fields__
                self.stats = CharityStats(**{k: v for k, v in data.items() if k in fields})
                if self.stats.contributions is None:
                    self.stats.contributions = []
                logger.info(
                    f"[NETERO] Chargé: ${self.stats.total_profit_real_usd:.2f} réels, "
                    f"${self.stats.total_profit_sim_usd:.2f} simulation"
                )
        except Exception as e:
            logger.warning(f"[NETERO] Could not load stats: {e}")


# Singleton global
_tracker: Optional[CharityTracker] = None


def get_charity_tracker() -> CharityTracker:
    global _tracker
    if _tracker is None:
        _tracker = CharityTracker()
    return _tracker
