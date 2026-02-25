"""
Whale Tracker - Détecte et suit les gros achats/ventes.

Fonctionnalités :
1. Détection des grosses transactions
2. Suivi des wallets "smart money"
3. Alertes sur mouvements suspects
4. Analyse des patterns de whales
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class WhaleTransaction:
    """Transaction de whale détectée."""
    tx_hash: str
    token_address: str
    token_symbol: str
    whale_address: str
    action: str  # "BUY" or "SELL"
    amount_tokens: float
    amount_usd: float
    price_impact: float
    timestamp: datetime
    chain: str


@dataclass
class WhaleAlert:
    """Alerte whale générée."""
    alert_type: str  # "large_buy", "large_sell", "accumulation", "distribution"
    token_address: str
    token_symbol: str
    severity: str  # "low", "medium", "high", "critical"
    message: str
    transactions: List[WhaleTransaction]
    recommendation: str  # "watch", "consider_buy", "consider_sell", "avoid"


class WhaleTracker:
    """Suit les mouvements des whales."""
    
    # Thresholds
    MIN_USD_FOR_WHALE = 10000  # $10k minimum pour être considéré whale
    LARGE_TX_THRESHOLD = 50000  # $50k = large transaction
    CRITICAL_TX_THRESHOLD = 200000  # $200k = critical
    
    # APIs
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
    
    # Known whale addresses to track (examples)
    KNOWN_WHALES = {
        # These would be updated with real whale addresses
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot Wallet",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    }
    
    def __init__(self):
        self._recent_txs: Dict[str, List[WhaleTransaction]] = defaultdict(list)
        self._whale_balances: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._alerts: List[WhaleAlert] = []
        
    async def track_token(
        self,
        token_address: str,
        chain: str = "ethereum"
    ) -> List[WhaleTransaction]:
        """
        Récupère les transactions récentes de whales pour un token.
        
        Returns:
            List of whale transactions
        """
        transactions = []
        
        try:
            # Get recent trades from DexScreener
            async with aiohttp.ClientSession() as session:
                url = f"{self.DEXSCREENER_API}/tokens/{token_address}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get("pairs", [])
                        
                        if not pairs:
                            return []
                        
                        main_pair = pairs[0]
                        symbol = main_pair.get("baseToken", {}).get("symbol", "???")
                        
                        # Analyze transaction data
                        txns = main_pair.get("txns", {})
                        h24 = txns.get("h24", {})
                        
                        buys = h24.get("buys", 0)
                        sells = h24.get("sells", 0)
                        
                        volume_24h = main_pair.get("volume", {}).get("h24", 0)
                        
                        # Estimate average tx size
                        total_txs = buys + sells
                        if total_txs > 0:
                            avg_tx_size = volume_24h / total_txs
                            
                            # If avg is high, likely whale activity
                            if avg_tx_size > self.MIN_USD_FOR_WHALE:
                                whale_tx = WhaleTransaction(
                                    tx_hash="aggregated",
                                    token_address=token_address,
                                    token_symbol=symbol,
                                    whale_address="unknown",
                                    action="MIXED",
                                    amount_tokens=0,
                                    amount_usd=avg_tx_size,
                                    price_impact=0,
                                    timestamp=datetime.now(),
                                    chain=chain
                                )
                                transactions.append(whale_tx)
                        
                        # Store for pattern analysis
                        self._recent_txs[token_address].extend(transactions)
                        
                        # Keep only last 100 per token
                        self._recent_txs[token_address] = self._recent_txs[token_address][-100:]
                        
            return transactions
            
        except Exception as e:
            logger.error(f"Whale tracking error for {token_address}: {e}")
            return []
    
    async def analyze_whale_activity(
        self,
        token_address: str,
        chain: str = "ethereum"
    ) -> Optional[WhaleAlert]:
        """
        Analyse l'activité whale et génère des alertes.
        
        Returns:
            WhaleAlert if significant activity detected
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.DEXSCREENER_API}/tokens/{token_address}"
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    pairs = data.get("pairs", [])
                    
                    if not pairs:
                        return None
                    
                    main_pair = pairs[0]
                    symbol = main_pair.get("baseToken", {}).get("symbol", "???")
                    
                    # Get transaction breakdown
                    txns = main_pair.get("txns", {})
                    
                    h1 = txns.get("h1", {})
                    h24 = txns.get("h24", {})
                    
                    buys_1h = h1.get("buys", 0)
                    sells_1h = h1.get("sells", 0)
                    buys_24h = h24.get("buys", 0)
                    sells_24h = h24.get("sells", 0)
                    
                    volume_1h = main_pair.get("volume", {}).get("h1", 0)
                    volume_24h = main_pair.get("volume", {}).get("h24", 0)
                    
                    price_change_1h = main_pair.get("priceChange", {}).get("h1", 0)
                    
                    # Analyze patterns
                    alert = None
                    
                    # Pattern 1: Large buy pressure
                    if buys_1h > sells_1h * 2 and volume_1h > self.MIN_USD_FOR_WHALE:
                        buy_ratio = buys_1h / max(sells_1h, 1)
                        severity = "high" if volume_1h > self.LARGE_TX_THRESHOLD else "medium"
                        
                        alert = WhaleAlert(
                            alert_type="large_buy",
                            token_address=token_address,
                            token_symbol=symbol,
                            severity=severity,
                            message=f"Strong buy pressure: {buy_ratio:.1f}x more buys than sells in 1h",
                            transactions=[],
                            recommendation="consider_buy"
                        )
                    
                    # Pattern 2: Large sell pressure (warning)
                    elif sells_1h > buys_1h * 2 and volume_1h > self.MIN_USD_FOR_WHALE:
                        sell_ratio = sells_1h / max(buys_1h, 1)
                        severity = "critical" if volume_1h > self.LARGE_TX_THRESHOLD else "high"
                        
                        alert = WhaleAlert(
                            alert_type="large_sell",
                            token_address=token_address,
                            token_symbol=symbol,
                            severity=severity,
                            message=f"Sell pressure warning: {sell_ratio:.1f}x more sells than buys in 1h",
                            transactions=[],
                            recommendation="avoid"
                        )
                    
                    # Pattern 3: Accumulation (steady buying over 24h)
                    elif buys_24h > sells_24h * 1.5 and volume_24h > self.LARGE_TX_THRESHOLD:
                        alert = WhaleAlert(
                            alert_type="accumulation",
                            token_address=token_address,
                            token_symbol=symbol,
                            severity="medium",
                            message=f"Accumulation detected: {buys_24h} buys vs {sells_24h} sells in 24h",
                            transactions=[],
                            recommendation="watch"
                        )
                    
                    # Pattern 4: Distribution (steady selling)
                    elif sells_24h > buys_24h * 1.5 and volume_24h > self.LARGE_TX_THRESHOLD:
                        alert = WhaleAlert(
                            alert_type="distribution",
                            token_address=token_address,
                            token_symbol=symbol,
                            severity="high",
                            message=f"Distribution pattern: {sells_24h} sells vs {buys_24h} buys in 24h",
                            transactions=[],
                            recommendation="consider_sell"
                        )
                    
                    if alert:
                        self._alerts.append(alert)
                        # Keep last 100 alerts
                        self._alerts = self._alerts[-100:]
                        
                        # Log
                        emoji = "🐋" if "buy" in alert.alert_type else "🔴"
                        logger.info(f"{emoji} Whale Alert [{symbol}]: {alert.message}")
                        logger.info(f"   Recommendation: {alert.recommendation}")
                    
                    return alert
                    
        except Exception as e:
            logger.error(f"Whale analysis error: {e}")
            return None
    
    async def get_whale_score(
        self,
        token_address: str,
        chain: str = "ethereum"
    ) -> Tuple[float, str]:
        """
        Calcule un score whale pour un token.
        
        Returns:
            Tuple[float, str]: (score 0-100, interpretation)
            Score > 70 = bullish whale activity
            Score < 30 = bearish whale activity
            Score 30-70 = neutral
        """
        alert = await self.analyze_whale_activity(token_address, chain)
        
        if not alert:
            return 50.0, "neutral"
        
        if alert.alert_type == "large_buy":
            if alert.severity == "high":
                return 85.0, "very_bullish"
            return 70.0, "bullish"
        
        elif alert.alert_type == "accumulation":
            return 65.0, "slightly_bullish"
        
        elif alert.alert_type == "large_sell":
            if alert.severity == "critical":
                return 10.0, "very_bearish"
            return 25.0, "bearish"
        
        elif alert.alert_type == "distribution":
            return 30.0, "slightly_bearish"
        
        return 50.0, "neutral"
    
    def get_recent_alerts(
        self,
        token_address: str = None,
        limit: int = 10
    ) -> List[WhaleAlert]:
        """Get recent whale alerts."""
        alerts = self._alerts
        
        if token_address:
            alerts = [a for a in alerts if a.token_address.lower() == token_address.lower()]
        
        return alerts[-limit:]
    
    def should_buy_based_on_whales(
        self,
        token_address: str,
        whale_score: float
    ) -> Tuple[bool, str]:
        """
        Décide si on devrait acheter basé sur l'activité whale.
        
        Returns:
            Tuple[bool, str]: (should_buy, reason)
        """
        if whale_score >= 70:
            return True, f"Bullish whale activity (score: {whale_score:.0f})"
        elif whale_score <= 30:
            return False, f"Bearish whale activity - avoid (score: {whale_score:.0f})"
        else:
            return True, f"Neutral whale activity (score: {whale_score:.0f})"


# Singleton
_tracker: Optional[WhaleTracker] = None


def get_whale_tracker() -> WhaleTracker:
    """Get or create whale tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = WhaleTracker()
    return _tracker
