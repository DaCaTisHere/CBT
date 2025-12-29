"""
Technical Indicators Module - Advanced Trading Indicators

Provides:
- MACD (Moving Average Convergence Divergence)
- EMA (Exponential Moving Average) 
- Stochastic RSI
- ATR (Average True Range)
- Bollinger Bands
- BTC Correlation
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import aiohttp
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IndicatorResult:
    """Result from indicator calculation"""
    value: float
    signal: str  # "bullish", "bearish", "neutral"
    strength: float  # 0-100


@dataclass
class FullAnalysis:
    """Complete technical analysis result"""
    symbol: str
    rsi: float
    stoch_rsi: float
    macd_signal: str  # "bullish", "bearish", "neutral"
    macd_histogram: float
    ema_trend: str  # "bullish", "bearish", "neutral"
    atr: float
    atr_percent: float
    btc_correlation: float
    overall_score: float  # 0-100
    recommendation: str  # "strong_buy", "buy", "hold", "sell", "strong_sell"


class TechnicalIndicators:
    """
    Calculate advanced technical indicators for trading decisions
    """
    
    def __init__(self):
        self.logger = logger
        self.price_cache: Dict[str, List[float]] = {}
        self.btc_prices: List[float] = []
        self.kline_cache: Dict[str, List[Dict]] = {}
        
    # ==================== RSI ====================
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index)
        
        RSI < 30 = Oversold (buy signal)
        RSI > 70 = Overbought (sell signal)
        """
        if len(prices) < period + 1:
            return 50.0
        
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
    
    # ==================== STOCHASTIC RSI ====================
    
    def calculate_stochastic_rsi(
        self, 
        prices: List[float], 
        rsi_period: int = 14,
        stoch_period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3
    ) -> Tuple[float, float]:
        """
        Calculate Stochastic RSI
        
        More sensitive than regular RSI.
        Returns (K%, D%)
        
        K < 20 = Oversold
        K > 80 = Overbought
        K crosses above D = Buy signal
        K crosses below D = Sell signal
        """
        if len(prices) < rsi_period + stoch_period + 1:
            return 50.0, 50.0
        
        # Calculate RSI values
        rsi_values = []
        for i in range(stoch_period + smooth_k + smooth_d):
            end_idx = len(prices) - i
            start_idx = max(0, end_idx - rsi_period - 1)
            if end_idx > start_idx:
                rsi = self.calculate_rsi(prices[start_idx:end_idx], rsi_period)
                rsi_values.insert(0, rsi)
        
        if len(rsi_values) < stoch_period:
            return 50.0, 50.0
        
        # Calculate Stochastic of RSI
        stoch_k_values = []
        for i in range(len(rsi_values) - stoch_period + 1):
            window = rsi_values[i:i + stoch_period]
            min_rsi = min(window)
            max_rsi = max(window)
            
            if max_rsi == min_rsi:
                stoch_k = 50.0
            else:
                stoch_k = ((rsi_values[i + stoch_period - 1] - min_rsi) / (max_rsi - min_rsi)) * 100
            stoch_k_values.append(stoch_k)
        
        # Smooth K
        if len(stoch_k_values) >= smooth_k:
            k = sum(stoch_k_values[-smooth_k:]) / smooth_k
        else:
            k = stoch_k_values[-1] if stoch_k_values else 50.0
        
        # Calculate D (smoothed K)
        if len(stoch_k_values) >= smooth_d:
            d = sum(stoch_k_values[-smooth_d:]) / smooth_d
        else:
            d = k
        
        return round(k, 2), round(d, 2)
    
    # ==================== MACD ====================
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def calculate_macd(
        self, 
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[float, float, float, str]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Returns (MACD Line, Signal Line, Histogram, Signal)
        
        MACD > Signal = Bullish
        MACD < Signal = Bearish
        Histogram positive & growing = Strong bullish
        Histogram negative & shrinking = Strong bearish
        """
        if len(prices) < slow_period + signal_period:
            return 0.0, 0.0, 0.0, "neutral"
        
        # Calculate EMAs
        fast_ema = self.calculate_ema(prices, fast_period)
        slow_ema = self.calculate_ema(prices, slow_period)
        
        # MACD Line
        macd_line = fast_ema - slow_ema
        
        # Calculate MACD values for signal line
        macd_values = []
        for i in range(signal_period + 5):
            end_idx = len(prices) - i
            if end_idx >= slow_period:
                fast = self.calculate_ema(prices[:end_idx], fast_period)
                slow = self.calculate_ema(prices[:end_idx], slow_period)
                macd_values.insert(0, fast - slow)
        
        # Signal Line (EMA of MACD)
        if len(macd_values) >= signal_period:
            signal_line = self.calculate_ema(macd_values, signal_period)
        else:
            signal_line = macd_line
        
        # Histogram
        histogram = macd_line - signal_line
        
        # Determine signal
        if macd_line > signal_line and histogram > 0:
            signal = "bullish"
        elif macd_line < signal_line and histogram < 0:
            signal = "bearish"
        else:
            signal = "neutral"
        
        return round(macd_line, 6), round(signal_line, 6), round(histogram, 6), signal
    
    # ==================== EMA CROSSOVER ====================
    
    def calculate_ema_crossover(
        self, 
        prices: List[float],
        fast_period: int = 9,
        slow_period: int = 21
    ) -> Tuple[str, float]:
        """
        Calculate EMA Crossover Signal
        
        Returns (signal, strength)
        
        Fast EMA > Slow EMA = Bullish trend
        Fast EMA < Slow EMA = Bearish trend
        Cross up = Buy signal
        Cross down = Sell signal
        """
        if len(prices) < slow_period + 2:
            return "neutral", 0.0
        
        # Current EMAs
        fast_ema = self.calculate_ema(prices, fast_period)
        slow_ema = self.calculate_ema(prices, slow_period)
        
        # Previous EMAs
        fast_ema_prev = self.calculate_ema(prices[:-1], fast_period)
        slow_ema_prev = self.calculate_ema(prices[:-1], slow_period)
        
        # Detect crossover
        current_diff = fast_ema - slow_ema
        prev_diff = fast_ema_prev - slow_ema_prev
        
        # Calculate strength as percentage difference
        strength = abs(current_diff / slow_ema * 100) if slow_ema != 0 else 0
        
        if current_diff > 0 and prev_diff <= 0:
            return "bullish_cross", min(strength * 10, 100)  # Golden cross
        elif current_diff < 0 and prev_diff >= 0:
            return "bearish_cross", min(strength * 10, 100)  # Death cross
        elif current_diff > 0:
            return "bullish", min(strength * 5, 100)
        elif current_diff < 0:
            return "bearish", min(strength * 5, 100)
        else:
            return "neutral", 0.0
    
    # ==================== ATR ====================
    
    def calculate_atr(
        self, 
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> float:
        """
        Calculate ATR (Average True Range)
        
        Measures volatility. Used for:
        - Dynamic stop-loss placement
        - Position sizing
        - Volatility filter
        """
        if len(highs) < period + 1:
            if highs and lows:
                return max(highs) - min(lows)
            return 0.0
        
        true_ranges = []
        
        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Calculate ATR (EMA of True Range)
        if len(true_ranges) >= period:
            atr = self.calculate_ema(true_ranges, period)
        else:
            atr = sum(true_ranges) / len(true_ranges)
        
        return round(atr, 6)
    
    def calculate_atr_percent(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> float:
        """Calculate ATR as percentage of current price"""
        if not closes:
            return 0.0
        
        atr = self.calculate_atr(highs, lows, closes, period)
        current_price = closes[-1]
        
        if current_price == 0:
            return 0.0
        
        return round((atr / current_price) * 100, 2)
    
    # ==================== BOLLINGER BANDS ====================
    
    def calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[float, float, float, str]:
        """
        Calculate Bollinger Bands
        
        Returns (upper, middle, lower, position)
        
        position:
        - "above_upper" = Overbought
        - "below_lower" = Oversold
        - "middle" = Normal
        """
        if len(prices) < period:
            return 0.0, 0.0, 0.0, "neutral"
        
        # Middle band (SMA)
        middle = sum(prices[-period:]) / period
        
        # Standard deviation
        variance = sum((p - middle) ** 2 for p in prices[-period:]) / period
        std = variance ** 0.5
        
        # Upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        # Current position
        current_price = prices[-1]
        
        if current_price > upper:
            position = "above_upper"
        elif current_price < lower:
            position = "below_lower"
        elif current_price > middle:
            position = "upper_half"
        else:
            position = "lower_half"
        
        return round(upper, 6), round(middle, 6), round(lower, 6), position
    
    # ==================== BTC CORRELATION ====================
    
    async def fetch_btc_trend(self) -> Tuple[str, float]:
        """
        Fetch BTC current trend
        
        Returns (trend, change_percent)
        
        Used to avoid trading against overall market direction.
        If BTC is dumping, skip long positions.
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        change = float(data.get('priceChangePercent', 0))
                        
                        if change > 2:
                            return "strong_bullish", change
                        elif change > 0.5:
                            return "bullish", change
                        elif change < -2:
                            return "strong_bearish", change
                        elif change < -0.5:
                            return "bearish", change
                        else:
                            return "neutral", change
        except Exception as e:
            self.logger.error(f"[INDICATORS] BTC trend error: {e}")
        
        return "neutral", 0.0
    
    async def fetch_klines(
        self, 
        symbol: str, 
        interval: str = "1h",
        limit: int = 100
    ) -> List[Dict]:
        """Fetch klines (candlestick) data from Binance"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.binance.com/api/v3/klines"
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        klines = []
                        for k in data:
                            klines.append({
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                                "timestamp": k[0]
                            })
                        return klines
        except Exception as e:
            self.logger.error(f"[INDICATORS] Klines error for {symbol}: {e}")
        
        return []
    
    # ==================== FULL ANALYSIS ====================
    
    async def analyze(self, symbol: str) -> Optional[FullAnalysis]:
        """
        Perform complete technical analysis on a symbol
        
        Returns comprehensive analysis with all indicators
        """
        try:
            # Fetch klines data
            klines = await self.fetch_klines(symbol, "1h", 100)
            
            if len(klines) < 30:
                return None
            
            # Extract price arrays
            closes = [k["close"] for k in klines]
            highs = [k["high"] for k in klines]
            lows = [k["low"] for k in klines]
            
            # Calculate all indicators
            rsi = self.calculate_rsi(closes)
            stoch_k, stoch_d = self.calculate_stochastic_rsi(closes)
            macd_line, signal_line, histogram, macd_signal = self.calculate_macd(closes)
            ema_trend, ema_strength = self.calculate_ema_crossover(closes)
            atr = self.calculate_atr(highs, lows, closes)
            atr_pct = self.calculate_atr_percent(highs, lows, closes)
            
            # BTC correlation
            btc_trend, btc_change = await self.fetch_btc_trend()
            btc_correlation = 1.0 if btc_trend in ["bullish", "strong_bullish"] else (
                -1.0 if btc_trend in ["bearish", "strong_bearish"] else 0.0
            )
            
            # Calculate overall score (0-100)
            score = 50.0  # Base score
            
            # RSI contribution (-20 to +20)
            if rsi <= 30:
                score += 20  # Oversold = buy
            elif rsi <= 40:
                score += 10
            elif rsi >= 70:
                score -= 20  # Overbought = sell
            elif rsi >= 60:
                score -= 10
            
            # Stochastic RSI contribution (-15 to +15)
            if stoch_k <= 20:
                score += 15  # Oversold
            elif stoch_k >= 80:
                score -= 15  # Overbought
            
            # MACD contribution (-15 to +15)
            if macd_signal == "bullish":
                score += 15
            elif macd_signal == "bearish":
                score -= 15
            
            # EMA trend contribution (-15 to +15)
            if "bullish" in ema_trend:
                score += 15 if "cross" in ema_trend else 10
            elif "bearish" in ema_trend:
                score -= 15 if "cross" in ema_trend else 10
            
            # BTC correlation contribution (-10 to +10)
            if btc_correlation > 0:
                score += 10  # Trade with BTC trend
            elif btc_correlation < 0:
                score -= 10  # Against BTC trend = risky
            
            # ATR penalty for high volatility
            if atr_pct > 10:
                score -= 10  # Too volatile
            
            # Clamp score
            score = max(0, min(100, score))
            
            # Determine recommendation
            if score >= 75:
                recommendation = "strong_buy"
            elif score >= 60:
                recommendation = "buy"
            elif score <= 25:
                recommendation = "strong_sell"
            elif score <= 40:
                recommendation = "sell"
            else:
                recommendation = "hold"
            
            return FullAnalysis(
                symbol=symbol,
                rsi=rsi,
                stoch_rsi=stoch_k,
                macd_signal=macd_signal,
                macd_histogram=histogram,
                ema_trend=ema_trend,
                atr=atr,
                atr_percent=atr_pct,
                btc_correlation=btc_correlation,
                overall_score=score,
                recommendation=recommendation
            )
            
        except Exception as e:
            self.logger.error(f"[INDICATORS] Analysis error for {symbol}: {e}")
            return None


# Global instance
_indicators: Optional[TechnicalIndicators] = None


def get_indicators() -> TechnicalIndicators:
    """Get global indicators instance"""
    global _indicators
    if _indicators is None:
        _indicators = TechnicalIndicators()
    return _indicators

