"""
AI Trading Engine - Le cerveau du bot qui combine tous les modules IA.

Intègre :
1. Honeypot Detection
2. Rug Pull Analysis
3. Sentiment Analysis
4. Smart Entry Timing
5. Dynamic Position Sizing
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TradeDecision(Enum):
    """Décisions de trading possibles."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WAIT = "wait"
    SKIP = "skip"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class AIAnalysisResult:
    """Résultat complet de l'analyse IA."""
    token_address: str
    token_symbol: str
    chain: str
    
    # Decision
    decision: TradeDecision
    confidence: float  # 0-1
    
    # Position sizing
    recommended_amount_usd: float
    stop_loss_percent: float
    take_profit_targets: List[float]
    
    # Scores
    security_score: float  # 0-100 (lower = safer)
    sentiment_score: float  # -1 to 1
    whale_score: float  # 0-100
    entry_score: float  # 0-1
    
    # Details
    reasoning: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Market data
    current_price: Optional[float] = None
    liquidity_usd: Optional[float] = None
    volume_24h: Optional[float] = None
    
    # Timing
    analysis_time_ms: float = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AITradingEngine:
    """
    Moteur de trading IA qui combine tous les modules pour
    prendre des décisions de trading optimales.
    """
    
    # Thresholds for decisions - AGGRESSIVE for real DEX trading
    # Tokens on DexScreener already passed basic listing checks
    CONFIDENCE_STRONG_BUY = 0.75
    CONFIDENCE_BUY = 0.60
    CONFIDENCE_WAIT = 0.45
    
    MAX_SECURITY_SCORE = 60  # Allow more risk for new tokens
    MIN_LIQUIDITY_USD = 3000  # Lower min for early sniper entries
    MIN_WHALE_SCORE = 15  # Most new tokens have no whale data
    
    def __init__(
        self,
        honeypot_detector=None,
        rugpull_detector=None,
        sentiment_analyzer=None,
        smart_entry_ai=None,
        position_sizer=None,
        dex_aggregator=None,
        whale_tracker=None,
    ):
        self.honeypot_detector = honeypot_detector
        self.rugpull_detector = rugpull_detector
        self.sentiment_analyzer = sentiment_analyzer
        self.smart_entry_ai = smart_entry_ai
        self.position_sizer = position_sizer
        self.dex_aggregator = dex_aggregator
        self.whale_tracker = whale_tracker
        
        self._trade_history: List[Dict] = []
        self._performance_stats = {
            "total_analyses": 0,
            "buys_recommended": 0,
            "skips_recommended": 0,
            "avg_confidence": 0,
        }
    
    async def analyze_token(
        self,
        token_address: str,
        token_symbol: str,
        chain: str,
        current_price: float,
        liquidity_usd: float,
        volume_24h: float = 0,
        ohlcv_data: List[Dict] = None,
        capital: float = 10000,
    ) -> AIAnalysisResult:
        """
        Analyse complète d'un token avec tous les modules IA.
        
        Returns:
            AIAnalysisResult avec décision et détails
        """
        start_time = datetime.now(timezone.utc)
        reasoning = []
        warnings = []
        
        # Initialize scores - START LOW for security (benefit of doubt)
        # External API failures should NOT block trades
        security_score = 25.0  # Assume safe until proven otherwise
        sentiment_score = 0.0
        whale_score = 50.0  # Neutral whale activity default
        entry_score = 0.5
        confidence = 0.35  # Must earn at least +0.25 from analysis to reach BUY (0.60)
        
        try:
            logger.info(f"🔍 Analyzing {token_symbol} ({token_address[:10]}...)")
            
            # ====== 1. SECURITY CHECKS — run honeypot + rugpull in parallel ======
            security_checks_attempted = 0
            security_checks_failed = 0
            
            async def _check_honeypot():
                nonlocal security_score, security_checks_attempted, security_checks_failed
                if not self.honeypot_detector:
                    return
                security_checks_attempted += 1
                try:
                    result = await self.honeypot_detector.check_token(token_address, chain)
                    if not result.get("is_safe", True):
                        hp_risk = result.get("details", {}).get("risk_score", 50)
                        if hp_risk >= 80:
                            warnings.append("HONEYPOT DETECTED")
                            security_score = 100
                        else:
                            security_score = hp_risk
                            reasoning.append(f"Moderate honeypot risk ({hp_risk}/100)")
                    else:
                        hp_risk = result.get("details", {}).get("risk_score", 25)
                        security_score = hp_risk
                        if hp_risk < 30:
                            reasoning.append("Passed honeypot check")
                        elif hp_risk < 50:
                            reasoning.append(f"Moderate honeypot risk ({hp_risk}/100)")
                except Exception as e:
                    logger.warning(f"Honeypot check error: {e}")
                    security_checks_failed += 1
            
            async def _check_rugpull():
                nonlocal security_score, security_checks_attempted, security_checks_failed
                if not self.rugpull_detector:
                    return
                security_checks_attempted += 1
                try:
                    rug_score, rug_details = await self.rugpull_detector.analyze(token_address, chain)
                    if rug_score >= 60:
                        security_score = max(security_score, rug_score)
                        warnings.append(f"High rug pull risk ({rug_score}/100)")
                    elif rug_score >= 40:
                        security_score = max(security_score, rug_score * 0.8)
                        warnings.append(f"Medium rug pull risk ({rug_score}/100)")
                    else:
                        reasoning.append(f"Low rug risk ({rug_score}/100)")
                    for f in rug_details.get("risk_factors", [])[:3]:
                        warnings.append(f"  - {f}")
                    for f in rug_details.get("safety_factors", [])[:2]:
                        reasoning.append(f"  + {f}")
                except Exception as e:
                    logger.warning(f"Rug pull check error: {e}")
                    security_checks_failed += 1
            
            await asyncio.gather(_check_honeypot(), _check_rugpull())
            
            # If ALL security checks failed (API errors), default to SKIP for safety
            if security_checks_attempted > 0 and security_checks_failed == security_checks_attempted:
                security_score = 80
                warnings.append("All security checks failed — defaulting to high risk")
                confidence -= 0.20
            
            # ====== 2. LIQUIDITY & VOLUME CHECK ======
            if liquidity_usd < self.MIN_LIQUIDITY_USD:
                warnings.append(f"⚠️ Low liquidity: ${liquidity_usd:,.0f}")
                confidence -= 0.20
            elif liquidity_usd > 200000:
                reasoning.append(f"✅ Excellent liquidity: ${liquidity_usd:,.0f}")
                confidence += 0.18
            elif liquidity_usd > 100000:
                reasoning.append(f"✅ Strong liquidity: ${liquidity_usd:,.0f}")
                confidence += 0.14
            elif liquidity_usd > 50000:
                reasoning.append(f"✅ Good liquidity: ${liquidity_usd:,.0f}")
                confidence += 0.10
            else:
                confidence += 0.03
            
            if volume_24h > 200000:
                reasoning.append(f"✅ Excellent volume: ${volume_24h:,.0f}")
                confidence += 0.18
            elif volume_24h > 100000:
                reasoning.append(f"✅ High volume: ${volume_24h:,.0f}")
                confidence += 0.14
            elif volume_24h > 50000:
                reasoning.append(f"✅ Good volume: ${volume_24h:,.0f}")
                confidence += 0.10
            elif volume_24h > 20000:
                reasoning.append(f"✅ Active volume: ${volume_24h:,.0f}")
                confidence += 0.05
            else:
                confidence -= 0.05
            
            # ====== 3-5. SENTIMENT + WHALE + ENTRY — run in parallel ======
            async def _check_sentiment():
                nonlocal sentiment_score, confidence
                if not self.sentiment_analyzer:
                    return
                try:
                    sentiment_score, _ = await self.sentiment_analyzer.analyze(token_symbol)
                    if sentiment_score > 0.3:
                        reasoning.append(f"Positive sentiment ({sentiment_score:.2f})")
                        confidence += 0.1
                    elif sentiment_score < -0.3:
                        warnings.append(f"Negative sentiment ({sentiment_score:.2f})")
                        confidence -= 0.15
                except Exception as e:
                    logger.warning(f"Sentiment error: {e}")
            
            async def _check_whales():
                nonlocal whale_score, confidence
                if not self.whale_tracker:
                    return
                try:
                    whale_score, _ = await self.whale_tracker.get_whale_score(token_address, chain)
                    if whale_score >= 70:
                        reasoning.append(f"Bullish whale activity ({whale_score:.0f})")
                        confidence += 0.12
                    elif whale_score <= 25:
                        warnings.append(f"Bearish whale activity ({whale_score:.0f})")
                        confidence -= 0.10
                except Exception as e:
                    logger.warning(f"Whale error: {e}")
            
            async def _check_entry():
                nonlocal entry_score, confidence
                if not (self.smart_entry_ai and ohlcv_data):
                    return
                try:
                    sig = await self.smart_entry_ai.analyze_entry(
                        token_address=token_address, current_price=current_price,
                        ohlcv_data=ohlcv_data, volume_24h=volume_24h,
                        liquidity_usd=liquidity_usd, sentiment_score=sentiment_score,
                        security_score=security_score)
                    entry_score = sig.confidence
                    if sig.action == "BUY":
                        reasoning.append(f"Entry signal: BUY ({entry_score:.2f})")
                        confidence += 0.1
                    elif sig.action == "WAIT":
                        reasoning.append(f"Entry signal: WAIT ({entry_score:.2f})")
                    else:
                        warnings.append(f"Entry signal: SKIP ({entry_score:.2f})")
                        confidence -= 0.15
                except Exception as e:
                    logger.warning(f"Smart entry error: {e}")
            
            await asyncio.gather(_check_sentiment(), _check_whales(), _check_entry())
            
            # ====== 6. POSITION SIZING ======
            recommended_amount = 50.0
            stop_loss = 10.0  # Cut losses faster
            take_profits = [15.0, 40.0, 80.0]  # TP1 at +15% to lock gains early
            
            if self.position_sizer:
                try:
                    self.position_sizer.update_capital(capital)
                    
                    # Determine token type
                    token_type = "normal" if security_score > 30 else "sniper"
                    if security_score < 20 and liquidity_usd > 100000:
                        token_type = "safe"
                    
                    position = self.position_sizer.calculate_position(
                        confidence=confidence,
                        risk_score=security_score,
                        liquidity_usd=liquidity_usd,
                        volatility=0.1,  # Default
                        stop_loss_percent=stop_loss,
                        token_type=token_type
                    )
                    
                    recommended_amount = position.amount_usd
                    reasoning.append(f"💰 Recommended: ${recommended_amount:.2f} ({position.percent_of_capital:.1f}%)")
                    
                except Exception as e:
                    logger.warning(f"Position sizing error: {e}")
            
            # ====== 7. FINAL DECISION ======
            
            # Security veto - confirmed honeypots
            if security_score >= 95:
                decision = TradeDecision.SKIP
                confidence = 0.0
                warnings.insert(0, "🚫 VETOED: Confirmed honeypot/scam")
            
            elif security_score >= 70:
                confidence -= 0.2
                warnings.insert(0, f"⚠️ High security risk ({security_score:.0f}) - reduced confidence")
            
            if whale_score <= 10 and security_score < 95:
                confidence = max(0, confidence - 0.25)
                warnings.insert(0, "⚠️ Extreme bearish whale activity")
            
            # Final decision based on confidence (always reached)
            if security_score >= 95:
                decision = TradeDecision.SKIP  # Already set above, explicit for clarity
            elif confidence >= self.CONFIDENCE_STRONG_BUY:
                decision = TradeDecision.STRONG_BUY
                reasoning.insert(0, f"🟢 STRONG BUY (confidence: {confidence:.2f})")
            elif confidence >= self.CONFIDENCE_BUY:
                decision = TradeDecision.BUY
                reasoning.insert(0, f"🟢 BUY (confidence: {confidence:.2f})")
            elif confidence >= self.CONFIDENCE_WAIT:
                decision = TradeDecision.WAIT
                reasoning.insert(0, f"🟡 WAIT (confidence: {confidence:.2f})")
            else:
                decision = TradeDecision.SKIP
                reasoning.insert(0, f"🔴 SKIP (confidence: {confidence:.2f})")
            
            # Cap confidence
            confidence = max(0.0, min(1.0, confidence))
            
            # Calculate analysis time
            analysis_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Update stats
            self._performance_stats["total_analyses"] += 1
            if decision in [TradeDecision.BUY, TradeDecision.STRONG_BUY]:
                self._performance_stats["buys_recommended"] += 1
            else:
                self._performance_stats["skips_recommended"] += 1
            
            result = AIAnalysisResult(
                token_address=token_address,
                token_symbol=token_symbol,
                chain=chain,
                decision=decision,
                confidence=confidence,
                recommended_amount_usd=recommended_amount,
                stop_loss_percent=stop_loss,
                take_profit_targets=take_profits,
                security_score=security_score,
                sentiment_score=sentiment_score,
                whale_score=whale_score,
                entry_score=entry_score,
                reasoning=reasoning,
                warnings=warnings,
                current_price=current_price,
                liquidity_usd=liquidity_usd,
                volume_24h=volume_24h,
                analysis_time_ms=analysis_time,
            )
            
            # Log result
            self._log_analysis(result)
            
            return result
            
        except Exception as e:
            logger.error(f"AI Analysis error for {token_symbol}: {e}")
            return AIAnalysisResult(
                token_address=token_address,
                token_symbol=token_symbol,
                chain=chain,
                decision=TradeDecision.SKIP,
                confidence=0.0,
                recommended_amount_usd=0,
                stop_loss_percent=15,
                take_profit_targets=[20, 50, 100],
                security_score=100,
                sentiment_score=0,
                whale_score=50,
                entry_score=0,
                reasoning=[],
                warnings=[f"❌ Analysis failed: {str(e)}"],
            )
    
    def _log_analysis(self, result: AIAnalysisResult):
        """Log the analysis result."""
        logger.info("=" * 60)
        logger.info(f"🤖 AI ANALYSIS: {result.token_symbol} on {result.chain}")
        logger.info("=" * 60)
        logger.info(f"Decision: {result.decision.value.upper()}")
        logger.info(f"Confidence: {result.confidence:.2f}")
        logger.info(f"Amount: ${result.recommended_amount_usd:.2f}")
        logger.info("-" * 40)
        logger.info(f"Security: {result.security_score:.0f}/100")
        logger.info(f"Sentiment: {result.sentiment_score:.2f}")
        logger.info(f"Whales: {result.whale_score:.0f}/100")
        logger.info(f"Entry: {result.entry_score:.2f}")
        logger.info("-" * 40)
        
        if result.reasoning:
            logger.info("Reasoning:")
            for r in result.reasoning[:5]:
                logger.info(f"  {r}")
        
        if result.warnings:
            logger.info("Warnings:")
            for w in result.warnings[:5]:
                logger.warning(f"  {w}")
        
        logger.info(f"Analysis time: {result.analysis_time_ms:.0f}ms")
        logger.info("=" * 60)
    
    def should_buy(self, result: AIAnalysisResult) -> Tuple[bool, str]:
        """Determine if we should buy, with explicit security gate."""
        if result.security_score >= 70:
            return False, f"Security risk too high ({result.security_score:.0f}/100)"
        if result.decision in [TradeDecision.STRONG_BUY, TradeDecision.BUY]:
            return True, f"{result.decision.value}: {result.reasoning[0] if result.reasoning else ''}"
        return False, f"{result.decision.value}: {result.warnings[0] if result.warnings else 'Low confidence'}"
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get engine performance statistics."""
        stats = self._performance_stats.copy()
        if stats["total_analyses"] > 0:
            stats["buy_rate"] = stats["buys_recommended"] / stats["total_analyses"] * 100
            stats["skip_rate"] = stats["skips_recommended"] / stats["total_analyses"] * 100
        return stats


# Factory function
def create_ai_trading_engine(
    web3_providers: Dict = None,
    capital: float = 10000,
) -> AITradingEngine:
    """
    Crée un moteur de trading IA complet avec tous les modules.
    """
    from ..security import honeypot_detector
    from ..security.rugpull_detector import RugPullDetector
    from .sentiment_analyzer import SentimentAnalyzer
    from .smart_entry import SmartEntryAI
    from .position_sizer import DynamicPositionSizer
    
    rugpull = RugPullDetector()
    sentiment = SentimentAnalyzer()
    smart_entry = SmartEntryAI()
    position_sizer = DynamicPositionSizer(capital)
    
    engine = AITradingEngine(
        honeypot_detector=honeypot_detector,
        rugpull_detector=rugpull,
        sentiment_analyzer=sentiment,
        smart_entry_ai=smart_entry,
        position_sizer=position_sizer,
    )
    
    logger.info("🤖 AI Trading Engine initialized with all modules")
    
    return engine
