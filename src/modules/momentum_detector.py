"""
Momentum Detector - Detect trading opportunities on existing cryptos

Detects:
- Volume spikes (unusual trading volume)
- Price breakouts (sudden price movements)
- Top gainers on Binance
- RSI-based momentum (avoid overbought conditions)
- MACD confirmation
- EMA trend analysis
- BTC correlation (trade with market direction)
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from src.utils.logger import get_logger
from src.utils.indicators import get_indicators, FullAnalysis
from src.core.config import settings

logger = get_logger(__name__)


@dataclass
class MomentumSignal:
    """A detected momentum signal with advanced technical analysis"""
    symbol: str
    signal_type: str  # volume_spike, breakout, top_gainer
    price: float
    change_percent: float
    volume_usd: float
    score: float  # 0-100 confidence score
    timestamp: datetime
    rsi: float = 50.0  # RSI value (30-70 is neutral)
    volatility: float = 0.0  # 24h volatility %
    # Advanced indicators
    stoch_rsi: float = 50.0  # Stochastic RSI (more sensitive)
    macd_signal: str = "neutral"  # "bullish", "bearish", "neutral"
    ema_trend: str = "neutral"  # "bullish", "bearish", "bullish_cross", "bearish_cross"
    btc_correlation: float = 0.0  # -1 (against BTC) to +1 (with BTC)
    atr_percent: float = 0.0  # ATR as % of price (for dynamic SL)
    ml_score: float = 0.0  # ML model prediction score


@dataclass
class TokenCooldown:
    """Track cooldown for tokens"""
    symbol: str
    last_trade_time: datetime
    cooldown_hours: float = 4.0  # Don't trade same token for 4h


class MomentumDetector:
    """
    Detect momentum opportunities on existing cryptocurrencies
    
    Strategies:
    1. Volume Spike: Detect when volume is 3x+ normal
    2. Breakout: Detect when price moves 5%+ quickly
    3. Top Gainers: Monitor Binance top gainers
    
    Advanced Filters:
    - RSI + Stochastic RSI
    - MACD confirmation
    - EMA trend direction
    - BTC correlation (trade with market)
    - ATR-based volatility filter
    """
    
    # Detection parameters - BALANCED for quality + quantity
    VOLUME_SPIKE_MULTIPLIER = 2.5  # 2.5x = good volume spikes (balanced)
    BREAKOUT_THRESHOLD_PCT = 4.0   # 4% = strong moves (slightly relaxed)
    MIN_VOLUME_USD = 300000        # $300k min - balanced (was $500k)
    TOP_GAINERS_COUNT = 30         # More candidates to evaluate (was 20)
    
    # RSI thresholds - OPTIMIZED for win rate
    RSI_OVERBOUGHT = 68  # Slightly stricter (was 70)
    RSI_OVERSOLD = 32    # Good entry opportunity
    RSI_NEUTRAL_HIGH = 58  # Earlier caution (was 60)
    
    # Stochastic RSI thresholds - OPTIMIZED
    STOCH_RSI_OVERBOUGHT = 75  # Stricter (was 80)
    STOCH_RSI_OVERSOLD = 25   # Slightly higher (was 20)
    
    # Volatility filter - BALANCED
    MAX_VOLATILITY_24H = 12.0  # Skip tokens > 12% volatility (stricter)
    
    # BTC correlation settings
    BTC_TREND_THRESHOLD = 0.3  # Lower threshold = more responsive
    REQUIRE_BTC_ALIGNMENT = True  # Only trade with BTC direction
    
    # Cooldown settings - OPTIMIZED
    TOKEN_COOLDOWN_HOURS = 6.0  # 6 hours cooldown (balanced)
    
    # Score requirements - OPTIMIZED for best win rate
    MIN_ADVANCED_SCORE = 72  # Balanced score (was 80, too strict)
    
    # Filters
    EXCLUDED_STABLECOINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP']
    # CRITICAL: Exclude leveraged tokens - they lose value over time due to daily rebalancing!
    EXCLUDED_LEVERAGED_SUFFIXES = ['DOWN', 'UP', 'BEAR', 'BULL', '3L', '3S', '2L', '2S']
    MIN_PRICE = 0.00000001
    MAX_PRICE = 100000
    
    def __init__(self):
        self.logger = logger
        self.is_running = False
        self.signals: List[MomentumSignal] = []
        self.processed_symbols: set = set()
        self.last_prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[float]] = {}  # For RSI calculation
        self.token_cooldowns: Dict[str, TokenCooldown] = {}  # Cooldown tracker
        
        # Advanced indicators
        self.indicators = get_indicators()
        self.btc_trend: str = "neutral"
        self.btc_change: float = 0.0
        self.last_btc_check: Optional[datetime] = None
        
        # Callbacks for signals
        self.signal_callbacks = []
        
        self.logger.info("[MOMENTUM] Detector initialized with FULL technical analysis")
    
    def on_signal(self, callback):
        """Register callback for new signals"""
        self.signal_callbacks.append(callback)
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index)
        
        RSI < 30 = Oversold (good buy)
        RSI > 70 = Overbought (avoid)
        """
        if len(prices) < period + 1:
            return 50.0  # Default to neutral
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def _calculate_volatility(self, high: float, low: float, close: float) -> float:
        """
        Calculate 24h volatility as percentage
        
        Volatility = (High - Low) / Close * 100
        """
        if close == 0:
            return 0.0
        return round(((high - low) / close) * 100, 2)
    
    def _is_token_on_cooldown(self, symbol: str) -> bool:
        """Check if token is on cooldown (recently traded)"""
        if symbol not in self.token_cooldowns:
            return False
        
        cooldown = self.token_cooldowns[symbol]
        elapsed = (datetime.utcnow() - cooldown.last_trade_time).total_seconds() / 3600
        
        return elapsed < self.TOKEN_COOLDOWN_HOURS
    
    def _is_leveraged_token(self, symbol: str) -> bool:
        """
        Check if token is a leveraged/inverse token
        
        These tokens are DANGEROUS for holding because they lose value
        over time due to daily rebalancing. Examples:
        - BTCDOWN, ETHUP, BNBBEAR, etc.
        - 3x leveraged: BTC3L, ETH3S
        
        NEVER trade these!
        """
        base = symbol.replace('USDT', '').replace('BTC', '').replace('ETH', '')
        
        for suffix in self.EXCLUDED_LEVERAGED_SUFFIXES:
            if base.endswith(suffix):
                return True
        
        # Also check for specific patterns
        if 'DOWN' in symbol or 'UP' in symbol:
            if symbol not in ['SETUPUSDT', 'SUPERUSDT']:  # False positives
                return True
        
        return False
    
    def set_token_cooldown(self, symbol: str):
        """Set cooldown for a token after trading it"""
        self.token_cooldowns[symbol] = TokenCooldown(
            symbol=symbol,
            last_trade_time=datetime.utcnow(),
            cooldown_hours=self.TOKEN_COOLDOWN_HOURS
        )
    
    async def _update_btc_trend(self):
        """Update BTC trend every 5 minutes"""
        now = datetime.utcnow()
        if self.last_btc_check and (now - self.last_btc_check).total_seconds() < 300:
            return  # Use cached value
        
        self.btc_trend, self.btc_change = await self.indicators.fetch_btc_trend()
        self.last_btc_check = now
        self.logger.info(f"[MOMENTUM] BTC Trend: {self.btc_trend} ({self.btc_change:+.2f}%)")
    
    async def _get_full_analysis(self, symbol: str) -> Optional[FullAnalysis]:
        """Get complete technical analysis for a symbol"""
        try:
            return await self.indicators.analyze(symbol)
        except Exception as e:
            self.logger.error(f"[MOMENTUM] Analysis error for {symbol}: {e}")
            return None
    
    def _calculate_advanced_score(
        self, 
        change_pct: float, 
        volume: float, 
        rsi: float,
        volatility: float,
        signal_type: str,
        stoch_rsi: float = 50.0,
        macd_signal: str = "neutral",
        ema_trend: str = "neutral",
        btc_aligned: bool = True,
        atr_percent: float = 0.0
    ) -> float:
        """
        Calculate ULTRA STRICT score - only best opportunities pass
        
        Score components (total 100 points):
        - Base score from price change (0-20)
        - Volume bonus (0-15)
        - RSI adjustment (-20 to +15) - MORE PENALTIES
        - Stochastic RSI bonus (-15 to +10) - MORE PENALTIES
        - MACD confirmation (-20 to +15) - MORE PENALTIES
        - EMA trend alignment (-15 to +10) - MORE PENALTIES
        - BTC correlation (-20 to +15) - MORE PENALTIES
        - Volatility/ATR penalty (0 to -20) - MORE PENALTIES
        - Signal type bonus (0-10)
        """
        score = 40.0  # Start LOWER (was 50) - be more strict
        
        # 1. Base score from price change (0-20 points)
        if 2 <= change_pct <= 8:
            base_score = 20  # Sweet spot
        elif 1 <= change_pct < 2:
            base_score = 10  # Early
        elif 8 < change_pct <= 15:
            base_score = 15  # Good but late
        else:
            base_score = 5
        score += base_score - 10  # Adjust to -5 to +10
        
        # 2. Volume bonus (0-15 points)
        if volume >= 2000000:  # $2M+
            score += 15
        elif volume >= 1000000:  # $1M+
            score += 12
        elif volume >= 500000:  # $500k+
            score += 8
        elif volume >= 200000:  # $200k+
            score += 4
        
        # 3. RSI adjustment (-20 to +15 points) - MORE STRICT PENALTIES
        if rsi <= self.RSI_OVERSOLD:
            score += 15  # Oversold = great buy
        elif rsi <= 40:
            score += 10
        elif rsi <= 50:
            score += 5
        elif rsi <= self.RSI_NEUTRAL_HIGH:
            score -= 10  # Caution (was -5, now -10)
        elif rsi <= self.RSI_OVERBOUGHT:
            score -= 15  # Avoid (was -10, now -15)
        else:
            score -= 20  # Overbought = REALLY avoid (was -15, now -20)
        
        # 4. Stochastic RSI bonus (-15 to +10 points) - MORE STRICT PENALTIES
        if stoch_rsi <= self.STOCH_RSI_OVERSOLD:
            score += 10  # Strong oversold
        elif stoch_rsi <= 35:
            score += 5
        elif stoch_rsi >= self.STOCH_RSI_OVERBOUGHT:
            score -= 15  # Strong overbought (was -10, now -15)
        elif stoch_rsi >= 65:
            score -= 10  # Caution (was -5, now -10)
        
        # 5. MACD confirmation (-20 to +15 points) - MORE STRICT PENALTIES
        if macd_signal == "bullish":
            score += 15
        elif macd_signal == "bearish":
            score -= 20  # Bearish = avoid more (was -15, now -20)
        # neutral = 0
        
        # 6. EMA trend alignment (-15 to +10 points) - MORE STRICT PENALTIES
        if ema_trend == "bullish_cross":
            score += 10  # Golden cross!
        elif ema_trend == "bullish":
            score += 5
        elif ema_trend == "bearish_cross":
            score -= 15  # Death cross (was -10, now -15)
        elif ema_trend == "bearish":
            score -= 10  # Bearish (was -5, now -10)
        
        # 7. BTC correlation (-20 to +15 points) - MORE STRICT PENALTIES
        if btc_aligned:
            if self.btc_trend == "strong_bullish":
                score += 15
            elif self.btc_trend == "bullish":
                score += 10
        else:
            if self.btc_trend == "strong_bearish":
                score -= 20  # Trading against dump (was -15, now -20)
            elif self.btc_trend == "bearish":
                score -= 15  # Against trend (was -10, now -15)
        
        # 8. Volatility/ATR penalty (0 to -20 points) - MORE STRICT PENALTIES
        effective_vol = max(volatility, atr_percent)
        if effective_vol > 15:  # Lowered threshold (was 20)
            score -= 20  # Too volatile (was -15, now -20)
        elif effective_vol > 12:  # Lowered threshold (was 15)
            score -= 15  # Very volatile (was -10, now -15)
        elif effective_vol > 8:  # Lowered threshold (was 10)
            score -= 10  # Volatile (was -5, now -10)
        
        # 9. Signal type bonus (0-10 points)
        if signal_type == "volume_spike":
            score += 10  # Best signal type
        elif signal_type == "breakout":
            score += 7
        else:
            score += 5  # top_gainer
        
        return max(0, min(100, score))
    
    async def start(self):
        """Start momentum detection"""
        self.is_running = True
        self.logger.info("[MOMENTUM] Starting momentum detection...")
        
        # Run detection loops
        await asyncio.gather(
            self._monitor_top_gainers(),
            self._monitor_volume_spikes(),
            return_exceptions=True
        )
    
    async def stop(self):
        """Stop momentum detection"""
        self.is_running = False
        self.logger.info("[MOMENTUM] Stopped")
    
    async def _monitor_top_gainers(self):
        """Monitor Binance top gainers with FULL technical analysis"""
        while self.is_running:
            try:
                # Update BTC trend first
                await self._update_btc_trend()
                
                # Skip if BTC is dumping hard
                if self.REQUIRE_BTC_ALIGNMENT and self.btc_trend == "strong_bearish":
                    self.logger.info("[MOMENTUM] Skipping scan: BTC strong bearish")
                    await asyncio.sleep(60)
                    continue
                
                gainers = await self._fetch_top_gainers()
                
                for gainer in gainers[:self.TOP_GAINERS_COUNT]:
                    symbol = gainer.get('symbol', '')
                    
                    # Skip stablecoins and already processed
                    base = symbol.replace('USDT', '').replace('BTC', '').replace('ETH', '')
                    if base in self.EXCLUDED_STABLECOINS:
                        continue
                    
                    # CRITICAL: Skip leveraged tokens (they lose value over time!)
                    if self._is_leveraged_token(symbol):
                        continue
                    
                    # Skip tokens on cooldown
                    if self._is_token_on_cooldown(symbol):
                        continue
                    
                    change_pct = float(gainer.get('priceChangePercent', 0))
                    price = float(gainer.get('lastPrice', 0))
                    volume = float(gainer.get('quoteVolume', 0))
                    high_price = float(gainer.get('highPrice', price))
                    low_price = float(gainer.get('lowPrice', price))
                    
                    # Basic filters first
                    if change_pct < 2 or volume < self.MIN_VOLUME_USD:
                        continue
                    
                    # Calculate basic volatility
                    volatility = self._calculate_volatility(high_price, low_price, price)
                    if volatility > self.MAX_VOLATILITY_24H:
                        continue
                    
                    # Calculate basic RSI
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    self.price_history[symbol].append(price)
                    self.price_history[symbol] = self.price_history[symbol][-20:]
                    rsi = self._calculate_rsi(self.price_history[symbol])
                    
                    if rsi > self.RSI_OVERBOUGHT:
                        continue
                    
                    # Check if not recently signaled
                    signal_key = f"{symbol}_{datetime.utcnow().strftime('%Y%m%d%H')}"
                    if signal_key in self.processed_symbols:
                        continue
                    
                    # === ADVANCED ANALYSIS ===
                    analysis = await self._get_full_analysis(symbol)
                    
                    # Default values if analysis fails
                    stoch_rsi = analysis.stoch_rsi if analysis else 50.0
                    macd_signal = analysis.macd_signal if analysis else "neutral"
                    ema_trend = analysis.ema_trend if analysis else "neutral"
                    atr_percent = analysis.atr_percent if analysis else 0.0
                    
                    # Check BTC alignment
                    btc_aligned = self.btc_trend in ["bullish", "strong_bullish", "neutral"]
                    
                    # Calculate FULL advanced score
                    score = self._calculate_advanced_score(
                        change_pct=change_pct,
                        volume=volume,
                        rsi=rsi,
                        volatility=volatility,
                        signal_type="top_gainer",
                        stoch_rsi=stoch_rsi,
                        macd_signal=macd_signal,
                        ema_trend=ema_trend,
                        btc_aligned=btc_aligned,
                        atr_percent=atr_percent
                    )
                    
                    # Only emit signal if score is high enough
                    if score >= self.MIN_ADVANCED_SCORE:
                        self.processed_symbols.add(signal_key)
                        
                        signal = MomentumSignal(
                            symbol=symbol,
                            signal_type="top_gainer",
                            price=price,
                            change_percent=change_pct,
                            volume_usd=volume,
                            score=score,
                            timestamp=datetime.utcnow(),
                            rsi=rsi,
                            volatility=volatility,
                            stoch_rsi=stoch_rsi,
                            macd_signal=macd_signal,
                            ema_trend=ema_trend,
                            btc_correlation=1.0 if btc_aligned else -1.0,
                            atr_percent=atr_percent
                        )
                        
                        await self._emit_signal(signal)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"[MOMENTUM] Top gainers error: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_volume_spikes(self):
        """Monitor for unusual volume spikes with FULL technical analysis"""
        while self.is_running:
            try:
                # Check BTC trend
                if self.REQUIRE_BTC_ALIGNMENT and self.btc_trend == "strong_bearish":
                    await asyncio.sleep(60)
                    continue
                
                tickers = await self._fetch_all_tickers()
                
                for ticker in tickers:
                    symbol = ticker.get('symbol', '')
                    if not symbol.endswith('USDT'):
                        continue
                    
                    base = symbol.replace('USDT', '')
                    if base in self.EXCLUDED_STABLECOINS:
                        continue
                    
                    # CRITICAL: Skip leveraged tokens (they lose value over time!)
                    if self._is_leveraged_token(symbol):
                        continue
                    
                    # Skip tokens on cooldown
                    if self._is_token_on_cooldown(symbol):
                        continue
                    
                    volume = float(ticker.get('quoteVolume', 0))
                    price = float(ticker.get('lastPrice', 0))
                    change_pct = float(ticker.get('priceChangePercent', 0))
                    high_price = float(ticker.get('highPrice', price))
                    low_price = float(ticker.get('lowPrice', price))
                    
                    # Basic volatility filter
                    volatility = self._calculate_volatility(high_price, low_price, price)
                    if volatility > self.MAX_VOLATILITY_24H:
                        continue
                    
                    # Update price history for RSI
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    self.price_history[symbol].append(price)
                    self.price_history[symbol] = self.price_history[symbol][-20:]
                    rsi = self._calculate_rsi(self.price_history[symbol])
                    
                    if rsi > self.RSI_OVERBOUGHT:
                        continue
                    
                    # Detect volume spike
                    prev_volume = self.last_prices.get(f"{symbol}_vol", 0)
                    
                    if prev_volume > 0 and volume > prev_volume * self.VOLUME_SPIKE_MULTIPLIER:
                        if volume >= self.MIN_VOLUME_USD and change_pct > 0:
                            signal_key = f"{symbol}_vol_{datetime.utcnow().strftime('%Y%m%d%H')}"
                            if signal_key not in self.processed_symbols:
                                
                                # === ADVANCED ANALYSIS ===
                                analysis = await self._get_full_analysis(symbol)
                                
                                stoch_rsi = analysis.stoch_rsi if analysis else 50.0
                                macd_signal = analysis.macd_signal if analysis else "neutral"
                                ema_trend = analysis.ema_trend if analysis else "neutral"
                                atr_percent = analysis.atr_percent if analysis else 0.0
                                
                                btc_aligned = self.btc_trend in ["bullish", "strong_bullish", "neutral"]
                                
                                # Calculate FULL advanced score
                                score = self._calculate_advanced_score(
                                    change_pct=change_pct,
                                    volume=volume,
                                    rsi=rsi,
                                    volatility=volatility,
                                    signal_type="volume_spike",
                                    stoch_rsi=stoch_rsi,
                                    macd_signal=macd_signal,
                                    ema_trend=ema_trend,
                                    btc_aligned=btc_aligned,
                                    atr_percent=atr_percent
                                )
                                
                                # Volume spikes get lower threshold (they're usually early signals)
                                if score >= self.MIN_ADVANCED_SCORE - 5:
                                    self.processed_symbols.add(signal_key)
                                    
                                    signal = MomentumSignal(
                                        symbol=symbol,
                                        signal_type="volume_spike",
                                        price=price,
                                        change_percent=change_pct,
                                        volume_usd=volume,
                                        score=score,
                                        timestamp=datetime.utcnow(),
                                        rsi=rsi,
                                        volatility=volatility,
                                        stoch_rsi=stoch_rsi,
                                        macd_signal=macd_signal,
                                        ema_trend=ema_trend,
                                        btc_correlation=1.0 if btc_aligned else -1.0,
                                        atr_percent=atr_percent
                                    )
                                    
                                    await self._emit_signal(signal)
                    
                    # Store for next comparison
                    self.last_prices[f"{symbol}_vol"] = volume
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"[MOMENTUM] Volume spike error: {e}")
                await asyncio.sleep(120)
    
    async def _fetch_top_gainers(self) -> List[Dict]:
        """Fetch top gainers from Binance"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.binance.com/api/v3/ticker/24hr"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Filter USDT pairs and sort by price change
                        usdt_pairs = [
                            t for t in data 
                            if t.get('symbol', '').endswith('USDT')
                            and float(t.get('priceChangePercent', 0)) > 0
                        ]
                        return sorted(
                            usdt_pairs,
                            key=lambda x: float(x.get('priceChangePercent', 0)),
                            reverse=True
                        )
        except Exception as e:
            self.logger.error(f"[MOMENTUM] Fetch gainers error: {e}")
        return []
    
    async def _fetch_all_tickers(self) -> List[Dict]:
        """Fetch all tickers from Binance"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.binance.com/api/v3/ticker/24hr"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            self.logger.error(f"[MOMENTUM] Fetch tickers error: {e}")
        return []
    
    async def _emit_signal(self, signal: MomentumSignal):
        """Emit a momentum signal with full technical analysis"""
        self.signals.append(signal)
        
        # Color code based on score
        if signal.score >= 70:
            emoji = "🟢"  # Strong buy
        elif signal.score >= 60:
            emoji = "🔵"  # Buy
        else:
            emoji = "🟡"  # Caution
        
        self.logger.info(
            f"[MOMENTUM] {emoji} SIGNAL: {signal.symbol} | "
            f"Type: {signal.signal_type} | "
            f"Change: {signal.change_percent:+.2f}% | "
            f"Volume: ${signal.volume_usd:,.0f} | "
            f"Score: {signal.score:.0f}/100"
        )
        self.logger.info(
            f"[MOMENTUM]   └── RSI: {signal.rsi:.0f} | "
            f"StochRSI: {signal.stoch_rsi:.0f} | "
            f"MACD: {signal.macd_signal} | "
            f"EMA: {signal.ema_trend} | "
            f"BTC: {'✓' if signal.btc_correlation > 0 else '✗'}"
        )
        
        # Notify callbacks
        for callback in self.signal_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                self.logger.error(f"[MOMENTUM] Callback error: {e}")
    
    def get_recent_signals(self, hours: int = 24) -> List[MomentumSignal]:
        """Get signals from the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [s for s in self.signals if s.timestamp >= cutoff]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        return {
            "is_running": self.is_running,
            "total_signals": len(self.signals),
            "signals_24h": len(self.get_recent_signals(24)),
            "symbols_tracked": len(self.last_prices) // 2
        }

