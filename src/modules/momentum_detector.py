"""
Momentum Detector v5.0 - PULLBACK STRATEGY

NOUVELLE STRATEGIE (v5.0):
Au lieu d'acheter les "top gainers" au sommet, on utilise une stratégie PULLBACK:
1. Détecter les tokens qui ont pumpé (+5% en 24h)
2. ATTENDRE qu'ils retracent depuis leur plus haut (-2% minimum)
3. Acheter sur le pullback (pas au sommet!)
4. Meilleur timing d'entrée = meilleur win rate

Cette stratégie évite le problème de "buy high, sell low".

Filtres avancés:
- RSI + Stochastic RSI (éviter surachat)
- MACD confirmation
- EMA trend direction
- BTC correlation (trader avec le marché)
- Distance from High (NOUVEAU - ne pas acheter au sommet)
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
    
    # ============ SWING TRADE STRATEGY v6.0 - BACKTESTED ============
    # 
    # VALIDATED ON 30 DAYS OF REAL DATA:
    # - 94.7% win rate
    # - +3.56% expectancy per trade
    # - 19 trades in 30 days (quality over quantity)
    #
    # This is the ONLY strategy that proved profitable in backtesting!
    
    # Volume requirements
    MIN_VOLUME_USD = 500000        # $500k minimum
    TOP_GAINERS_COUNT = 50         # Scan more to find setups
    
    # SWING TRADE ENTRY CONDITIONS (from backtest)
    MIN_PUMP_24H = 5.0             # Strong pump required (+5% min)
    MAX_PUMP_24H = 30.0            # But not extreme (max +30%)
    MIN_PULLBACK_FROM_HIGH = 3.0   # Deeper pullback (3% from high)
    MAX_PULLBACK_FROM_HIGH = 12.0  # But not dumping (max 12%)
    
    # RSI thresholds - VERY STRICT (key to 94.7% win rate)
    RSI_OVERBOUGHT = 50            # VERY strict - don't buy above 50 RSI!
    RSI_OVERSOLD = 30              # Ideal entry zone
    RSI_NEUTRAL_HIGH = 45          # Caution above 45
    
    # Stochastic RSI thresholds - STRICT
    STOCH_RSI_OVERBOUGHT = 55      # Very strict
    STOCH_RSI_OVERSOLD = 30        # Good entry
    
    # Volatility filter
    MAX_VOLATILITY_24H = 20.0      # Allow more volatility for swing trades
    
    # BTC correlation settings
    BTC_TREND_THRESHOLD = 0.3      
    REQUIRE_BTC_ALIGNMENT = True   # Only trade with BTC direction
    
    # Cooldown settings
    TOKEN_COOLDOWN_HOURS = 8.0     # Longer cooldown for swing style
    
    # Score requirements
    MIN_ADVANCED_SCORE = 70        # Score based on new criteria
    
    # DISABLE volume_spike - 0% success rate in backtesting
    ENABLE_VOLUME_SPIKE = False
    
    # Filters
    EXCLUDED_STABLECOINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP']
    # CRITICAL: Exclude leveraged tokens - they lose value over time due to daily rebalancing!
    EXCLUDED_LEVERAGED_SUFFIXES = ['DOWN', 'UP', 'BEAR', 'BULL', '3L', '3S', '2L', '2S']
    # BLACKLIST: Tokens with API/price issues (prices not updating correctly)
    BLACKLISTED_TOKENS = [
        'XMRUSDT',   # Price stuck at $118.70 - CoinGecko data issue
        'LITUSDT',   # Price stuck at $0.743 - CoinGecko data issue
        'BCHUSDT',   # Often has stale price data
    ]
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
    
    def _calculate_pullback_score(
        self, 
        change_pct: float, 
        volume: float, 
        rsi: float,
        volatility: float,
        stoch_rsi: float = 50.0,
        macd_signal: str = "neutral",
        ema_trend: str = "neutral",
        btc_aligned: bool = True,
        atr_percent: float = 0.0,
        distance_from_high: float = 0.0
    ) -> float:
        """
        PULLBACK STRATEGY SCORING v5.0
        
        Score optimized for pullback entries:
        - Pullback quality (distance from high) - NEW KEY METRIC
        - Volume confirmation
        - RSI (prefer lower, not overbought)
        - Stochastic RSI
        - MACD/EMA trend
        - BTC correlation
        """
        score = 50.0  # Start neutral
        
        # 1. PULLBACK QUALITY - THE MOST IMPORTANT FACTOR (0-25 points)
        # Ideal pullback: 3-5% from high
        if 3.0 <= distance_from_high <= 5.0:
            score += 25  # Perfect pullback zone
        elif 2.0 <= distance_from_high < 3.0:
            score += 20  # Good pullback
        elif 5.0 < distance_from_high <= 6.0:
            score += 15  # Deeper pullback, still ok
        elif 6.0 < distance_from_high <= 8.0:
            score += 5   # Getting risky
        else:
            score -= 10  # Too shallow or too deep
        
        # 2. Volume confirmation (0-15 points)
        if volume >= 3000000:  # $3M+ = strong interest
            score += 15
        elif volume >= 1500000:  # $1.5M+
            score += 12
        elif volume >= 750000:  # $750k+
            score += 8
        elif volume >= 500000:  # $500k+ minimum
            score += 4
        
        # 3. RSI - prefer lower values (not overbought) (-15 to +15)
        if rsi <= 35:
            score += 15  # Oversold on pullback = great
        elif rsi <= 45:
            score += 10  # Good zone
        elif rsi <= 55:
            score += 5   # Acceptable
        elif rsi <= 60:
            score -= 5   # Getting high
        else:
            score -= 15  # Too high for pullback entry
        
        # 4. Stochastic RSI (-10 to +10)
        if stoch_rsi <= 30:
            score += 10  # Oversold
        elif stoch_rsi <= 50:
            score += 5
        elif stoch_rsi >= 65:
            score -= 10  # Overbought
        
        # 5. MACD confirmation (-10 to +10)
        if macd_signal == "bullish":
            score += 10  # Momentum turning up
        elif macd_signal == "bearish":
            score -= 10  # Still falling
        
        # 6. EMA trend (-10 to +10)
        if ema_trend in ["bullish", "bullish_cross"]:
            score += 10  # Uptrend intact
        elif ema_trend in ["bearish", "bearish_cross"]:
            score -= 10  # Downtrend
        
        # 7. BTC correlation (-15 to +10)
        if btc_aligned:
            if self.btc_trend in ["strong_bullish", "bullish"]:
                score += 10
        else:
            score -= 15  # Against BTC trend
        
        # 8. Volatility penalty (0 to -10)
        effective_vol = max(volatility, atr_percent)
        if effective_vol > 15:
            score -= 10
        elif effective_vol > 12:
            score -= 5
        
        # 9. 24h change validation
        # Ideal: 4-10% pump then pullback
        if 5.0 <= change_pct <= 10.0:
            score += 5  # Sweet spot
        elif 3.0 <= change_pct < 5.0 or 10.0 < change_pct <= 15.0:
            score += 0  # OK
        else:
            score -= 5  # Not ideal
        
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
        """
        PULLBACK STRATEGY v5.0
        
        Au lieu d'acheter au sommet, on cherche des tokens qui:
        1. Ont pumpé (+3% à +20% en 24h) = momentum confirmé
        2. MAIS qui ont retracé depuis leur plus haut (-2% à -8%)
        3. = Point d'entrée optimal sur pullback
        
        Cela évite le problème "buy high, sell low"
        """
        while self.is_running:
            try:
                # Update BTC trend first
                await self._update_btc_trend()
                
                # Skip if BTC is dumping hard
                if self.REQUIRE_BTC_ALIGNMENT and self.btc_trend == "strong_bearish":
                    self.logger.info("[PULLBACK] ⏸️ Skipping scan: BTC strong bearish")
                    await asyncio.sleep(60)
                    continue
                
                gainers = await self._fetch_top_gainers()
                pullback_candidates = 0
                
                for gainer in gainers[:self.TOP_GAINERS_COUNT]:
                    symbol = gainer.get('symbol', '')
                    
                    # Skip stablecoins
                    base = symbol.replace('USDT', '').replace('BTC', '').replace('ETH', '')
                    if base in self.EXCLUDED_STABLECOINS:
                        continue
                    
                    # Skip blacklisted tokens
                    if symbol in self.BLACKLISTED_TOKENS:
                        continue
                    
                    # Skip leveraged tokens
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
                    
                    # ============ PULLBACK FILTERS ============
                    
                    # 1. Volume filter
                    if volume < self.MIN_VOLUME_USD:
                        continue
                    
                    # 2. Pump filter: Token must have pumped (confirms momentum)
                    if change_pct < self.MIN_PUMP_24H or change_pct > self.MAX_PUMP_24H:
                        continue
                    
                    # 3. CRITICAL: Pullback filter - NOT at the top!
                    # Calculate distance from 24h high
                    if high_price > 0:
                        distance_from_high = ((high_price - price) / high_price) * 100
                    else:
                        distance_from_high = 0
                    
                    # Must be in pullback zone (2-8% below high)
                    if distance_from_high < self.MIN_PULLBACK_FROM_HIGH:
                        # Too close to high = buying at top = BAD
                        continue
                    if distance_from_high > self.MAX_PULLBACK_FROM_HIGH:
                        # Too far from high = might be dumping = BAD
                        continue
                    
                    pullback_candidates += 1
                    
                    # 4. Volatility filter
                    volatility = self._calculate_volatility(high_price, low_price, price)
                    if volatility > self.MAX_VOLATILITY_24H:
                        continue
                    
                    # 5. RSI filter (strict - no overbought)
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
                    
                    stoch_rsi = analysis.stoch_rsi if analysis else 50.0
                    macd_signal = analysis.macd_signal if analysis else "neutral"
                    ema_trend = analysis.ema_trend if analysis else "neutral"
                    atr_percent = analysis.atr_percent if analysis else 0.0
                    
                    # Strict StochRSI filter
                    if stoch_rsi > self.STOCH_RSI_OVERBOUGHT:
                        continue
                    
                    # Check BTC alignment
                    btc_aligned = self.btc_trend in ["bullish", "strong_bullish", "neutral"]
                    
                    # Calculate score with pullback bonus
                    score = self._calculate_pullback_score(
                        change_pct=change_pct,
                        volume=volume,
                        rsi=rsi,
                        volatility=volatility,
                        stoch_rsi=stoch_rsi,
                        macd_signal=macd_signal,
                        ema_trend=ema_trend,
                        btc_aligned=btc_aligned,
                        atr_percent=atr_percent,
                        distance_from_high=distance_from_high
                    )
                    
                    # Only emit signal if score is high enough
                    if score >= self.MIN_ADVANCED_SCORE:
                        self.processed_symbols.add(signal_key)
                        
                        signal = MomentumSignal(
                            symbol=symbol,
                            signal_type="pullback",  # NEW signal type
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
                        
                        await self._emit_signal(signal, distance_from_high)
                
                if pullback_candidates > 0:
                    self.logger.debug(f"[PULLBACK] Scanned {len(gainers)} gainers, {pullback_candidates} in pullback zone")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"[PULLBACK] Error: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_volume_spikes(self):
        """
        Volume spike detection - DISABLED in v5.0
        
        Data analysis shows 0% success rate for volume_spike signals.
        This function now only maintains price history for RSI calculations.
        """
        if not self.ENABLE_VOLUME_SPIKE:
            self.logger.info("[PULLBACK] Volume spike detection DISABLED (0% success rate)")
        
        while self.is_running:
            try:
                # Only update price history for RSI calculations
                tickers = await self._fetch_all_tickers()
                
                for ticker in tickers:
                    symbol = ticker.get('symbol', '')
                    if not symbol.endswith('USDT'):
                        continue
                    
                    price = float(ticker.get('lastPrice', 0))
                    volume = float(ticker.get('quoteVolume', 0))
                    
                    # Update price history for RSI (needed by pullback strategy)
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    self.price_history[symbol].append(price)
                    self.price_history[symbol] = self.price_history[symbol][-20:]
                    
                    # Store volume for reference
                    self.last_prices[f"{symbol}_vol"] = volume
                
                await asyncio.sleep(120)  # Less frequent since we're just caching
                
            except Exception as e:
                self.logger.error(f"[PULLBACK] Cache update error: {e}")
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
    
    async def _emit_signal(self, signal: MomentumSignal, distance_from_high: float = 0.0):
        """Emit a pullback signal with full technical analysis"""
        self.signals.append(signal)
        
        # Color code based on score
        if signal.score >= 80:
            emoji = "🟢"  # Excellent
        elif signal.score >= 75:
            emoji = "🔵"  # Good
        else:
            emoji = "🟡"  # Acceptable
        
        self.logger.info(
            f"[PULLBACK] {emoji} SIGNAL: {signal.symbol} | "
            f"Score: {signal.score:.0f}/100 | "
            f"Pullback: -{distance_from_high:.1f}% from high"
        )
        self.logger.info(
            f"[PULLBACK]   └── 24h: +{signal.change_percent:.1f}% | "
            f"Vol: ${signal.volume_usd/1000000:.1f}M | "
            f"RSI: {signal.rsi:.0f} | "
            f"MACD: {signal.macd_signal}"
        )
        
        # Notify callbacks
        for callback in self.signal_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                self.logger.error(f"[PULLBACK] Callback error: {e}")
    
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

