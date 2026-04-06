"""
Dynamic Position Sizer - Ajuste la taille des positions selon le risque.

Stratégies :
1. Kelly Criterion (optimisé)
2. Fixed fractional
3. Volatility-based
4. Confidence-based
"""
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Résultat du calcul de taille de position."""
    amount_usd: float
    percent_of_capital: float
    risk_amount: float
    reasoning: str
    strategy_used: str


class DynamicPositionSizer:
    """Calcule dynamiquement la taille optimale des positions."""
    
    # Limites de sécurité
    MIN_POSITION_USD = 10
    MAX_POSITION_PERCENT = 10  # Max 10% du capital par trade
    MIN_POSITION_PERCENT = 0.5  # Min 0.5% du capital
    
    # Risk parameters
    DEFAULT_RISK_PER_TRADE = 2  # 2% du capital risqué par trade
    MAX_RISK_PER_TRADE = 5  # Max 5% risqué
    
    def __init__(self, total_capital: float):
        """
        Args:
            total_capital: Capital total disponible
        """
        self.total_capital = total_capital
        self._trade_history: list = []
        self._win_rate = 0.5  # Default 50%
        self._avg_win = 0.3   # Default 30% win
        self._avg_loss = 0.15  # Default 15% loss
        
    def update_capital(self, new_capital: float):
        """Met à jour le capital total."""
        self.total_capital = new_capital
        logger.info(f"💰 Capital updated: ${new_capital:,.2f}")
    
    def calculate_position(
        self,
        confidence: float,
        risk_score: float,
        liquidity_usd: float,
        volatility: float = 0.1,
        stop_loss_percent: float = 15.0,
        token_type: str = "normal"
    ) -> PositionSize:
        """
        Calcule la taille de position optimale.
        
        Args:
            confidence: Confiance du signal (0-1)
            risk_score: Score de risque du token (0-100)
            liquidity_usd: Liquidité disponible
            volatility: Volatilité du token
            stop_loss_percent: Stop loss en %
            token_type: "normal", "sniper", "safe"
            
        Returns:
            PositionSize avec le montant recommandé
        """
        reasoning_parts = []
        
        # 1. Base position using fixed fractional
        base_percent = self.DEFAULT_RISK_PER_TRADE
        
        # 2. Adjust for confidence (Kelly-inspired)
        # Higher confidence = larger position
        confidence_multiplier = 0.5 + confidence  # 0.5x to 1.5x
        adjusted_percent = base_percent * confidence_multiplier
        reasoning_parts.append(f"Confidence adj: {confidence_multiplier:.2f}x")
        
        # 3. Adjust for risk score
        # Higher risk = smaller position
        if risk_score >= 50:
            risk_multiplier = 0.3  # Very risky
            reasoning_parts.append(f"High risk ({risk_score}): 0.3x")
        elif risk_score >= 30:
            risk_multiplier = 0.6
            reasoning_parts.append(f"Medium risk ({risk_score}): 0.6x")
        else:
            risk_multiplier = 1.0
            reasoning_parts.append(f"Low risk ({risk_score}): 1.0x")
        
        adjusted_percent *= risk_multiplier
        
        # 4. Adjust for volatility
        # Higher volatility = smaller position
        if volatility > 0.2:
            vol_multiplier = 0.5
            reasoning_parts.append(f"High volatility: 0.5x")
        elif volatility > 0.1:
            vol_multiplier = 0.75
            reasoning_parts.append(f"Medium volatility: 0.75x")
        else:
            vol_multiplier = 1.0
        
        adjusted_percent *= vol_multiplier
        
        # 5. Token type adjustments
        if token_type == "sniper":
            # Sniper = smaller, more aggressive positions
            adjusted_percent *= 0.5
            reasoning_parts.append("Sniper mode: 0.5x")
        elif token_type == "safe":
            # Safe = larger positions
            adjusted_percent *= 1.5
            reasoning_parts.append("Safe mode: 1.5x")
        
        # 6. Apply limits
        adjusted_percent = max(self.MIN_POSITION_PERCENT, adjusted_percent)
        adjusted_percent = min(self.MAX_POSITION_PERCENT, adjusted_percent)
        
        # 7. Calculate USD amount
        amount_usd = self.total_capital * (adjusted_percent / 100)
        
        # 8. Check against liquidity (don't take more than 2% of pool)
        max_from_liquidity = liquidity_usd * 0.02
        if amount_usd > max_from_liquidity:
            amount_usd = max_from_liquidity
            reasoning_parts.append(f"Limited by liquidity: ${amount_usd:.2f}")
        
        # 9. Apply minimum
        amount_usd = max(self.MIN_POSITION_USD, amount_usd)
        
        # Calculate actual percent and risk
        actual_percent = (amount_usd / self.total_capital) * 100
        risk_amount = amount_usd * (stop_loss_percent / 100)
        
        strategy = "dynamic_fractional"
        reasoning = " | ".join(reasoning_parts)
        
        result = PositionSize(
            amount_usd=round(amount_usd, 2),
            percent_of_capital=round(actual_percent, 2),
            risk_amount=round(risk_amount, 2),
            reasoning=reasoning,
            strategy_used=strategy
        )
        
        logger.info(f"📊 Position size: ${result.amount_usd} ({result.percent_of_capital}% of capital)")
        logger.info(f"   Risk: ${result.risk_amount} | {reasoning}")
        
        return result
    
    def calculate_kelly(
        self,
        win_rate: float = None,
        avg_win: float = None,
        avg_loss: float = None
    ) -> float:
        """
        Calcule la fraction Kelly optimale.
        
        Returns:
            Fraction optimale du capital à risquer (0-1)
        """
        # Use provided or historical values
        w = win_rate if win_rate else self._win_rate
        avg_w = avg_win if avg_win else self._avg_win
        avg_l = avg_loss if avg_loss else self._avg_loss
        
        if avg_l == 0 or avg_w == 0:
            return 0.0

        # Kelly = W - (1-W)/R where R = avg_win/avg_loss
        r = avg_w / avg_l
        if r == 0:
            return 0.0
        kelly = w - ((1 - w) / r)
        
        # Use half-Kelly for safety
        half_kelly = kelly / 2
        
        # Cap at reasonable level
        return max(0, min(0.25, half_kelly))  # Max 25%
    
    def update_stats(
        self,
        won: bool,
        profit_percent: float
    ):
        """Met à jour les statistiques après un trade."""
        self._trade_history.append({
            "won": won,
            "profit": profit_percent
        })
        
        # Keep last 100 trades
        if len(self._trade_history) > 100:
            self._trade_history = self._trade_history[-100:]
        
        # Recalculate stats
        if self._trade_history:
            wins = [t for t in self._trade_history if t["won"]]
            losses = [t for t in self._trade_history if not t["won"]]
            
            self._win_rate = len(wins) / len(self._trade_history)
            self._avg_win = np.mean([t["profit"] for t in wins]) if wins else 0.3
            self._avg_loss = abs(np.mean([t["profit"] for t in losses])) if losses else 0.15
            
            logger.info(f"📈 Stats updated: WR={self._win_rate:.1%}, AvgW={self._avg_win:.1%}, AvgL={self._avg_loss:.1%}")
    
    def get_recommended_sizes(self) -> Dict[str, float]:
        """Retourne les tailles recommandées par type de trade."""
        return {
            "sniper_new_token": self.calculate_position(
                confidence=0.6,
                risk_score=40,
                liquidity_usd=20000,
                token_type="sniper"
            ).amount_usd,
            "normal_trade": self.calculate_position(
                confidence=0.7,
                risk_score=25,
                liquidity_usd=100000,
                token_type="normal"
            ).amount_usd,
            "high_confidence": self.calculate_position(
                confidence=0.9,
                risk_score=15,
                liquidity_usd=500000,
                token_type="safe"
            ).amount_usd,
        }


# Singleton
_sizer: Optional[DynamicPositionSizer] = None


def get_position_sizer(capital: float = 10000) -> DynamicPositionSizer:
    """Get or create position sizer singleton."""
    global _sizer
    if _sizer is None:
        _sizer = DynamicPositionSizer(capital)
    return _sizer
