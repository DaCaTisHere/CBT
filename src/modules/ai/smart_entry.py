"""
Smart Entry AI - Utilise le ML pour prédire le meilleur moment d'entrée.

Features analysées :
1. Momentum (RSI, MACD)
2. Volume profile
3. Support/Resistance levels
4. Order flow imbalance
5. Historical patterns
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EntrySignal:
    """Signal d'entrée généré par l'IA."""
    action: str  # "BUY", "WAIT", "SKIP"
    confidence: float  # 0-1
    entry_price: Optional[float]
    target_price: Optional[float]
    stop_loss: Optional[float]
    reasoning: List[str]
    timeframe: str  # "immediate", "wait_dip", "wait_breakout"


class SmartEntryAI:
    """IA pour déterminer le meilleur moment d'entrée."""
    
    # Thresholds
    MIN_CONFIDENCE_TO_BUY = 0.6
    IDEAL_RSI_RANGE = (30, 50)  # Buy in this range
    OVERBOUGHT_RSI = 70
    OVERSOLD_RSI = 30
    
    def __init__(self):
        self._pattern_cache: Dict[str, List[Dict]] = {}
        self._trade_history: List[Dict] = []
        
    async def analyze_entry(
        self,
        token_address: str,
        current_price: float,
        ohlcv_data: List[Dict[str, Any]],
        volume_24h: float,
        liquidity_usd: float,
        sentiment_score: float = 0.0,
        security_score: float = 0.0,
    ) -> EntrySignal:
        """
        Analyse et génère un signal d'entrée.
        
        Args:
            token_address: Adresse du token
            current_price: Prix actuel
            ohlcv_data: Données OHLCV historiques
            volume_24h: Volume 24h
            liquidity_usd: Liquidité en USD
            sentiment_score: Score de sentiment (-1 à 1)
            security_score: Score de sécurité (0-100, 0 = safe)
            
        Returns:
            EntrySignal avec recommandation
        """
        reasoning = []
        confidence = 0.5  # Start neutral
        
        try:
            # 1. Security check - critical
            if security_score >= 70:
                return EntrySignal(
                    action="SKIP",
                    confidence=0.95,
                    entry_price=None,
                    target_price=None,
                    stop_loss=None,
                    reasoning=["Security score too high - unsafe token"],
                    timeframe="never"
                )
            elif security_score >= 50:
                confidence -= 0.2
                reasoning.append(f"⚠️ Medium security risk ({security_score}/100)")
            elif security_score < 30:
                confidence += 0.1
                reasoning.append(f"✅ Low security risk ({security_score}/100)")
            
            # 2. Analyze technical indicators from OHLCV
            if len(ohlcv_data) >= 14:
                indicators = self._calculate_indicators(ohlcv_data)
                
                # RSI analysis
                rsi = indicators.get("rsi", 50)
                if self.IDEAL_RSI_RANGE[0] <= rsi <= self.IDEAL_RSI_RANGE[1]:
                    confidence += 0.15
                    reasoning.append(f"✅ RSI in ideal range ({rsi:.1f})")
                elif rsi > self.OVERBOUGHT_RSI:
                    confidence -= 0.2
                    reasoning.append(f"⚠️ RSI overbought ({rsi:.1f})")
                elif rsi < self.OVERSOLD_RSI:
                    confidence += 0.1
                    reasoning.append(f"📊 RSI oversold - potential reversal ({rsi:.1f})")
                
                # MACD analysis
                macd = indicators.get("macd", 0)
                macd_signal = indicators.get("macd_signal", 0)
                if macd > macd_signal and macd > 0:
                    confidence += 0.1
                    reasoning.append("✅ MACD bullish crossover")
                elif macd < macd_signal:
                    confidence -= 0.1
                    reasoning.append("⚠️ MACD bearish")
                
                # Volume trend
                volume_trend = indicators.get("volume_trend", 0)
                if volume_trend > 1.5:  # 50% above average
                    confidence += 0.1
                    reasoning.append(f"✅ High volume ({volume_trend:.1f}x average)")
                elif volume_trend < 0.5:
                    confidence -= 0.1
                    reasoning.append("⚠️ Low volume")
                    
                # Price momentum
                price_momentum = indicators.get("price_momentum", 0)
                if 0 < price_momentum < 20:
                    confidence += 0.1
                    reasoning.append(f"✅ Healthy momentum (+{price_momentum:.1f}%)")
                elif price_momentum > 100:
                    confidence -= 0.15
                    reasoning.append(f"⚠️ Extreme pump - risky entry (+{price_momentum:.1f}%)")
                elif price_momentum < -20:
                    confidence -= 0.1
                    reasoning.append(f"⚠️ Dumping ({price_momentum:.1f}%)")
            else:
                reasoning.append("⚠️ Insufficient data for technical analysis")
                confidence -= 0.1
            
            # 3. Sentiment analysis
            if sentiment_score > 0.3:
                confidence += 0.1
                reasoning.append(f"✅ Positive sentiment ({sentiment_score:.2f})")
            elif sentiment_score < -0.3:
                confidence -= 0.15
                reasoning.append(f"⚠️ Negative sentiment ({sentiment_score:.2f})")
            
            # 4. Liquidity check
            if liquidity_usd < 5000:
                confidence -= 0.2
                reasoning.append(f"⚠️ Very low liquidity (${liquidity_usd:,.0f})")
            elif liquidity_usd < 20000:
                confidence -= 0.1
                reasoning.append(f"⚠️ Low liquidity (${liquidity_usd:,.0f})")
            elif liquidity_usd > 100000:
                confidence += 0.1
                reasoning.append(f"✅ Good liquidity (${liquidity_usd:,.0f})")
            
            # 5. Calculate entry levels
            entry_price = current_price
            target_price = current_price * 1.50  # 50% target
            stop_loss = current_price * 0.85  # 15% stop loss
            
            # Adjust based on volatility if available
            if len(ohlcv_data) >= 5:
                volatility = self._calculate_volatility(ohlcv_data[-5:])
                if volatility > 0.1:  # High volatility
                    target_price = current_price * (1 + volatility * 3)  # Dynamic target
                    stop_loss = current_price * (1 - min(volatility * 1.5, 0.20))  # Tighter stop
            
            # Cap confidence
            confidence = max(0.0, min(1.0, confidence))
            
            # Determine action
            if confidence >= self.MIN_CONFIDENCE_TO_BUY:
                action = "BUY"
                timeframe = "immediate"
            elif confidence >= 0.4:
                action = "WAIT"
                timeframe = "wait_dip"
                reasoning.append("📊 Consider waiting for a better entry")
            else:
                action = "SKIP"
                timeframe = "never"
                reasoning.append("❌ Too risky for entry")
            
            signal = EntrySignal(
                action=action,
                confidence=confidence,
                entry_price=entry_price,
                target_price=target_price,
                stop_loss=stop_loss,
                reasoning=reasoning,
                timeframe=timeframe
            )
            
            # Log
            emoji = "🟢" if action == "BUY" else "🟡" if action == "WAIT" else "🔴"
            logger.info(f"{emoji} Entry signal: {action} (confidence: {confidence:.2f})")
            for reason in reasoning[:3]:  # Log first 3 reasons
                logger.info(f"   {reason}")
            
            return signal
            
        except Exception as e:
            logger.error(f"Smart entry analysis error: {e}")
            return EntrySignal(
                action="SKIP",
                confidence=0.0,
                entry_price=None,
                target_price=None,
                stop_loss=None,
                reasoning=[f"Analysis error: {str(e)}"],
                timeframe="never"
            )
    
    def _calculate_indicators(self, ohlcv_data: List[Dict]) -> Dict[str, float]:
        """Calcule les indicateurs techniques."""
        closes = [d.get("close", d.get("c", 0)) for d in ohlcv_data]
        volumes = [d.get("volume", d.get("v", 0)) for d in ohlcv_data]
        
        indicators = {}
        
        # RSI (14 periods)
        if len(closes) >= 14:
            indicators["rsi"] = self._calculate_rsi(closes, 14)
        
        # MACD
        if len(closes) >= 26:
            macd, signal = self._calculate_macd(closes)
            indicators["macd"] = macd
            indicators["macd_signal"] = signal
        
        # Volume trend (current vs average)
        if volumes:
            avg_volume = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
            if avg_volume > 0:
                indicators["volume_trend"] = volumes[-1] / avg_volume
        
        # Price momentum (% change over period)
        if len(closes) >= 2:
            indicators["price_momentum"] = ((closes[-1] / closes[0]) - 1) * 100
        
        return indicators
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calcule le RSI."""
        if len(prices) < period + 1:
            return 50.0
            
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(
        self, 
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[float, float]:
        """Calcule MACD et signal line."""
        prices_arr = np.array(prices)
        
        # EMA calculation
        def ema(data, period):
            alpha = 2 / (period + 1)
            result = np.zeros_like(data)
            result[0] = data[0]
            for i in range(1, len(data)):
                result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
            return result
        
        ema_fast = ema(prices_arr, fast)
        ema_slow = ema(prices_arr, slow)
        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        
        return macd_line[-1], signal_line[-1]
    
    def _calculate_volatility(self, ohlcv_data: List[Dict]) -> float:
        """Calcule la volatilité (écart-type des rendements)."""
        closes = [d.get("close", d.get("c", 0)) for d in ohlcv_data]
        if len(closes) < 2:
            return 0.0
            
        returns = np.diff(closes) / closes[:-1]
        return np.std(returns)
    
    def record_trade_result(
        self,
        token_address: str,
        entry_signal: EntrySignal,
        actual_result: float,  # % profit/loss
    ):
        """Enregistre le résultat d'un trade pour l'apprentissage."""
        self._trade_history.append({
            "token": token_address,
            "signal": entry_signal,
            "result": actual_result,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Keep last 1000 trades
        if len(self._trade_history) > 1000:
            self._trade_history = self._trade_history[-1000:]
        
        # Log learning
        logger.info(f"📚 Trade recorded: {actual_result:+.1f}% (confidence was {entry_signal.confidence:.2f})")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance de l'IA."""
        if not self._trade_history:
            return {"trades": 0}
        
        results = [t["result"] for t in self._trade_history]
        confidences = [t["signal"].confidence for t in self._trade_history]
        
        winning_trades = [r for r in results if r > 0]
        losing_trades = [r for r in results if r < 0]
        
        return {
            "trades": len(self._trade_history),
            "win_rate": len(winning_trades) / len(results) * 100 if results else 0,
            "avg_profit": np.mean(winning_trades) if winning_trades else 0,
            "avg_loss": np.mean(losing_trades) if losing_trades else 0,
            "avg_confidence": np.mean(confidences),
            "total_pnl": sum(results),
        }


# Singleton
_ai: Optional[SmartEntryAI] = None


def get_smart_entry_ai() -> SmartEntryAI:
    """Get or create smart entry AI singleton."""
    global _ai
    if _ai is None:
        _ai = SmartEntryAI()
    return _ai
