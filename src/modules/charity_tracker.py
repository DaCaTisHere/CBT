"""
Charity Tracker - Mission Humanitaire

Suit les profits générés par le bot et calcule la part destinée
aux associations d'aide humanitaire.

Architecture :
- Chaque trade rentable est enregistré
- 10% des profits nets sont alloués aux associations
- Tableau de bord dédié dans le dashboard
- Notifications Telegram pour chaque jalon humanitaire
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

# Pourcentage des profits alloués aux associations
CHARITY_RATE = 0.10  # 10%

# Jalons de notification (en USD alloués à la charité)
CHARITY_MILESTONES = [1, 5, 10, 25, 50, 100, 250, 500, 1000]

# Associations humanitaires soutenues
SUPPORTED_CHARITIES = [
    {
        "name": "Médecins Sans Frontières",
        "description": "Soins médicaux dans les zones de conflit",
        "url": "https://www.msf.fr",
        "focus": "Santé",
        "emoji": "🏥",
    },
    {
        "name": "UNICEF",
        "description": "Protection de l'enfance dans le monde",
        "url": "https://www.unicef.fr",
        "focus": "Enfance",
        "emoji": "🧒",
    },
    {
        "name": "Action Contre la Faim",
        "description": "Lutte contre la malnutrition",
        "url": "https://www.actioncontrelafaim.org",
        "focus": "Alimentation",
        "emoji": "🍲",
    },
    {
        "name": "Croix-Rouge",
        "description": "Aide humanitaire d'urgence mondiale",
        "url": "https://www.croix-rouge.fr",
        "focus": "Urgences",
        "emoji": "🔴",
    },
    {
        "name": "Oxfam France",
        "description": "Lutte contre les inégalités et la pauvreté",
        "url": "https://www.oxfamfrance.org",
        "focus": "Inégalités",
        "emoji": "✊",
    },
]


@dataclass
class CharityStats:
    # Totaux cumulés
    total_profit_usd: float = 0.0          # Total des profits du bot
    total_charity_allocated_usd: float = 0.0  # 10% alloués à la charité
    total_trades_profitable: int = 0        # Nombre de trades gagnants
    total_trades_total: int = 0             # Nombre total de trades

    # Progression vers le prochain jalon
    last_milestone_reached: float = 0.0    # Dernier jalon atteint en USD
    next_milestone: float = 1.0            # Prochain jalon à atteindre

    # Historique des trades contributeurs
    contributions: List[Dict] = None       # Dernières 50 contributions

    # Mode de trading
    is_simulation: bool = True             # True = virtuel, False = réel

    # Métadonnées
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        if self.contributions is None:
            self.contributions = []
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class CharityTracker:
    """
    Suit les profits du bot et alloue une part aux associations humanitaires.

    Usage:
        tracker = get_charity_tracker()
        tracker.record_profit(pnl_usd=25.50, symbol="ETHUSDT", is_simulation=True)
        stats = tracker.get_stats()
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
        """Enregistre un callback async pour les jalons humanitaires."""
        self._notifier = callback

    def record_trade(
        self,
        pnl_usd: float,
        symbol: str,
        strategy: str = "momentum",
        is_simulation: bool = True,
    ) -> Optional[float]:
        """
        Enregistre un trade et calcule l'allocation charité si positif.

        Returns:
            charity_amount_usd si profit, None si perte.
        """
        self.stats.total_trades_total += 1

        if pnl_usd <= 0:
            self._save()
            return None

        charity_amount = round(pnl_usd * CHARITY_RATE, 4)

        self.stats.total_profit_usd = round(self.stats.total_profit_usd + pnl_usd, 4)
        self.stats.total_charity_allocated_usd = round(
            self.stats.total_charity_allocated_usd + charity_amount, 4
        )
        self.stats.total_trades_profitable += 1
        self.stats.is_simulation = is_simulation

        # Log contribution
        contribution = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "strategy": strategy,
            "pnl_usd": round(pnl_usd, 4),
            "charity_usd": charity_amount,
            "is_simulation": is_simulation,
        }
        self.stats.contributions.append(contribution)
        # Keep only last 50
        self.stats.contributions = self.stats.contributions[-50:]

        # Check milestone
        self._check_milestone()
        self._save()

        logger.info(
            f"[CHARITY] +${charity_amount:.4f} alloué | "
            f"Total: ${self.stats.total_charity_allocated_usd:.2f} | "
            f"{'(simulation)' if is_simulation else '(REEL)'}"
        )

        return charity_amount

    def _check_milestone(self):
        """Vérifie si un jalon humanitaire est franchi."""
        total = self.stats.total_charity_allocated_usd
        for milestone in sorted(CHARITY_MILESTONES):
            if total >= milestone > self.stats.last_milestone_reached:
                self.stats.last_milestone_reached = milestone
                logger.info(
                    f"[CHARITY] 🎉 JALON ATTEINT: ${milestone} alloués aux associations !"
                )
                if self._notifier:
                    try:
                        import asyncio
                        asyncio.get_running_loop().create_task(
                            self._notifier("milestone", {"amount": milestone, "total": total})
                        )
                    except RuntimeError:
                        pass

        # Update next milestone
        remaining = [m for m in CHARITY_MILESTONES if m > self.stats.last_milestone_reached]
        self.stats.next_milestone = remaining[0] if remaining else CHARITY_MILESTONES[-1]

    def get_stats(self) -> Dict:
        """Retourne les statistiques humanitaires pour le dashboard."""
        total = self.stats.total_charity_allocated_usd
        next_m = self.stats.next_milestone
        last_m = self.stats.last_milestone_reached

        # Progression vers le prochain jalon (0-100%)
        if next_m > last_m:
            progress_pct = min(100.0, ((total - last_m) / (next_m - last_m)) * 100)
        else:
            progress_pct = 100.0

        return {
            "total_profit_usd": self.stats.total_profit_usd,
            "total_charity_usd": self.stats.total_charity_allocated_usd,
            "charity_rate_pct": CHARITY_RATE * 100,
            "total_trades": self.stats.total_trades_total,
            "profitable_trades": self.stats.total_trades_profitable,
            "win_rate": (
                (self.stats.total_trades_profitable / self.stats.total_trades_total * 100)
                if self.stats.total_trades_total > 0 else 0.0
            ),
            "last_milestone": self.stats.last_milestone_reached,
            "next_milestone": self.stats.next_milestone,
            "progress_to_next_milestone_pct": progress_pct,
            "is_simulation": self.stats.is_simulation,
            "recent_contributions": self.stats.contributions[-10:],
            "charities": SUPPORTED_CHARITIES,
            "last_updated": self.stats.last_updated,
        }

    def get_impact_message(self) -> str:
        """Retourne un message d'impact humanitaire."""
        total = self.stats.total_charity_allocated_usd
        if total <= 0:
            return "Aucun profit encore — les associations attendent !"
        if total < 5:
            return f"${total:.2f} accumulés pour les associations humanitaires"
        if total < 25:
            return f"${total:.2f} — de quoi financer des repas pour des familles"
        if total < 100:
            return f"${total:.2f} — l'équivalent de consultations médicales"
        if total < 500:
            return f"${total:.2f} — de quoi aider des dizaines de personnes"
        return f"${total:.2f} — impact humanitaire significatif !"

    def _save(self):
        self.stats.last_updated = datetime.now(timezone.utc).isoformat()
        try:
            with open(_CHARITY_FILE, "w") as f:
                json.dump(asdict(self.stats), f, indent=2)
        except Exception as e:
            logger.warning(f"[CHARITY] Could not save stats: {e}")

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
                    f"[CHARITY] Loaded: ${self.stats.total_charity_allocated_usd:.2f} alloués"
                )
        except Exception as e:
            logger.warning(f"[CHARITY] Could not load stats: {e}")


# Singleton global
_tracker: Optional[CharityTracker] = None


def get_charity_tracker() -> CharityTracker:
    global _tracker
    if _tracker is None:
        _tracker = CharityTracker()
    return _tracker
