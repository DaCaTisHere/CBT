"""
Auto-Learning System for CryptoBot

This module automatically:
1. Records every trade with its features (indicators, signals)
2. Trains a ML model on historical trade outcomes
3. Uses the model to score new signals
4. Re-trains periodically to improve predictions

The bot learns from its own mistakes and successes!
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    """Record of a trade with all features for ML training"""
    # Trade info
    symbol: str
    entry_time: str
    exit_time: Optional[str] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl_percent: float = 0.0
    is_profitable: bool = False
    exit_reason: str = ""
    
    # Signal features (captured at entry)
    signal_type: str = ""
    signal_score: float = 0.0
    change_percent: float = 0.0
    volume_usd: float = 0.0
    
    # Technical indicators (captured at entry)
    rsi: float = 50.0
    stoch_rsi: float = 50.0
    macd_signal: str = "neutral"
    ema_trend: str = "neutral"
    atr_percent: float = 0.0
    
    # Market context
    btc_correlation: float = 0.0
    volatility_24h: float = 0.0
    hour_of_day: int = 0
    day_of_week: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TradeRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AutoLearner:
    """
    Auto-learning system that improves trading decisions over time
    
    Features:
    - Records all trades with their features
    - Trains a lightweight model (no heavy ML dependencies)
    - Scores new signals based on learned patterns
    - Re-trains every N hours automatically
    """
    
    # Configuration
    DATA_DIR = "data/ml"
    TRADES_FILE = "trade_records.json"
    MODEL_FILE = "learned_patterns.json"
    MIN_TRADES_FOR_TRAINING = 20  # Minimum trades before model is useful
    RETRAIN_INTERVAL_HOURS = 6   # Re-train every 6 hours
    
    def __init__(self):
        self.logger = logger
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Trade records
        self.trade_records: List[TradeRecord] = []
        
        # Learned patterns (simple but effective)
        self.patterns = {
            # Feature importance weights (learned from data)
            "weights": {
                "score": 0.3,
                "rsi": 0.15,
                "stoch_rsi": 0.1,
                "macd": 0.15,
                "ema": 0.1,
                "volume": 0.1,
                "btc_correlation": 0.1
            },
            # Optimal ranges learned from profitable trades
            "optimal_ranges": {
                "rsi_min": 30,
                "rsi_max": 65,
                "stoch_rsi_max": 75,
                "score_min": 60,
                "volume_min": 100000,
                "change_min": 1.0,
                "change_max": 15.0
            },
            # Pattern success rates
            "signal_type_success": {},  # e.g., {"volume_spike": 0.65, "breakout": 0.45}
            "macd_success": {},         # e.g., {"bullish": 0.6, "neutral": 0.4}
            "ema_success": {},
            "hour_success": {},         # Success rate by hour
            "day_success": {},          # Success rate by day of week
            
            # Stats
            "total_trades": 0,
            "profitable_trades": 0,
            "avg_win_pnl": 0.0,
            "avg_loss_pnl": 0.0,
            "win_rate": 0.0,
            "last_trained": None
        }
        
        self.is_trained = False
        self.is_running = False
        self._retrain_task: Optional[asyncio.Task] = None
        
        self.logger.info("[ML] AutoLearner initialized")
    
    async def initialize(self):
        """Load existing data and start auto-retraining"""
        await self._load_data()
        await self._load_patterns()
        
        # Count completed trades (with exit time)
        completed_trades = [t for t in self.trade_records if t.exit_time is not None]
        
        # Force training if enough completed trades
        if len(completed_trades) >= self.MIN_TRADES_FOR_TRAINING:
            self.logger.info(f"[ML] 🔄 Force training on {len(completed_trades)} completed trades...")
            await self.train()
        
        self.logger.info(f"[ML] Loaded {len(self.trade_records)} trade records ({len(completed_trades)} completed)")
        self.logger.info(f"[ML] Model trained: {self.is_trained}")
    
    async def start(self):
        """Start auto-retraining loop"""
        self.is_running = True
        self._retrain_task = asyncio.create_task(self._retrain_loop())
        self.logger.info("[ML] Auto-retraining started")
    
    async def stop(self):
        """Stop auto-retraining"""
        self.is_running = False
        if self._retrain_task:
            self._retrain_task.cancel()
        await self._save_data()
        await self._save_patterns()
        self.logger.info("[ML] AutoLearner stopped")
    
    async def _retrain_loop(self):
        """Periodically retrain the model"""
        while self.is_running:
            try:
                await asyncio.sleep(self.RETRAIN_INTERVAL_HOURS * 3600)
                
                if len(self.trade_records) >= self.MIN_TRADES_FOR_TRAINING:
                    self.logger.info("[ML] 🔄 Auto-retraining started...")
                    await self.train()
                    self.logger.info("[ML] ✅ Auto-retraining complete")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[ML] Retrain loop error: {e}")
                await asyncio.sleep(60)
    
    # ==================== DATA COLLECTION ====================
    
    def record_entry(
        self,
        symbol: str,
        price: float,
        signal_type: str = "",
        signal_score: float = 0.0,
        change_percent: float = 0.0,
        volume_usd: float = 0.0,
        rsi: float = 50.0,
        stoch_rsi: float = 50.0,
        macd_signal: str = "neutral",
        ema_trend: str = "neutral",
        atr_percent: float = 0.0,
        btc_correlation: float = 0.0,
        volatility_24h: float = 0.0
    ) -> TradeRecord:
        """Record a new trade entry with all features"""
        now = datetime.utcnow()
        
        record = TradeRecord(
            symbol=symbol,
            entry_time=now.isoformat(),
            entry_price=price,
            signal_type=signal_type,
            signal_score=signal_score,
            change_percent=change_percent,
            volume_usd=volume_usd,
            rsi=rsi,
            stoch_rsi=stoch_rsi,
            macd_signal=macd_signal,
            ema_trend=ema_trend,
            atr_percent=atr_percent,
            btc_correlation=btc_correlation,
            volatility_24h=volatility_24h,
            hour_of_day=now.hour,
            day_of_week=now.weekday()
        )
        
        self.trade_records.append(record)
        self.logger.debug(f"[ML] Recorded entry: {symbol} @ ${price:.6f}")
        
        # Auto-save periodically
        if len(self.trade_records) % 10 == 0:
            asyncio.create_task(self._save_data())
        
        return record
    
    def record_exit(
        self,
        symbol: str,
        exit_price: float,
        pnl_percent: float,
        exit_reason: str
    ):
        """Record a trade exit and mark outcome"""
        # Find the most recent open trade for this symbol
        found = False
        for record in reversed(self.trade_records):
            if record.symbol == symbol and record.exit_time is None:
                record.exit_time = datetime.utcnow().isoformat()
                record.exit_price = exit_price
                record.pnl_percent = pnl_percent
                record.is_profitable = pnl_percent > 0
                record.exit_reason = exit_reason
                
                self.logger.info(
                    f"[ML] ✅ Recorded exit: {symbol} | "
                    f"PnL: {'+' if pnl_percent > 0 else ''}{pnl_percent:.2f}% | "
                    f"Reason: {exit_reason}"
                )
                
                # Trigger save
                asyncio.create_task(self._save_data())
                found = True
                break
        
        if not found:
            self.logger.warning(f"[ML] ⚠️ No open entry found for {symbol} exit! This trade won't be learned from.")
    
    # ==================== TRAINING ====================
    
    async def train(self):
        """Train the model on historical trades"""
        completed_trades = [t for t in self.trade_records if t.exit_time is not None]
        
        if len(completed_trades) < self.MIN_TRADES_FOR_TRAINING:
            self.logger.warning(f"[ML] Not enough trades for training ({len(completed_trades)}/{self.MIN_TRADES_FOR_TRAINING})")
            return
        
        self.logger.info(f"[ML] Training on {len(completed_trades)} completed trades...")
        
        # Calculate basic stats
        profitable = [t for t in completed_trades if t.is_profitable]
        losing = [t for t in completed_trades if not t.is_profitable]
        
        self.patterns["total_trades"] = len(completed_trades)
        self.patterns["profitable_trades"] = len(profitable)
        self.patterns["win_rate"] = len(profitable) / len(completed_trades) if completed_trades else 0
        
        if profitable:
            self.patterns["avg_win_pnl"] = np.mean([t.pnl_percent for t in profitable])
        if losing:
            self.patterns["avg_loss_pnl"] = np.mean([t.pnl_percent for t in losing])
        
        # Learn optimal ranges from profitable trades
        await self._learn_optimal_ranges(profitable)
        
        # Learn signal type success rates
        await self._learn_categorical_success(completed_trades, "signal_type", "signal_type_success")
        await self._learn_categorical_success(completed_trades, "macd_signal", "macd_success")
        await self._learn_categorical_success(completed_trades, "ema_trend", "ema_success")
        await self._learn_hour_patterns(completed_trades)
        
        # Update feature weights based on correlation with profitability
        await self._learn_feature_weights(completed_trades)
        
        self.patterns["last_trained"] = datetime.utcnow().isoformat()
        self.is_trained = True
        
        await self._save_patterns()
        
        self.logger.info(f"[ML] Training complete!")
        self.logger.info(f"[ML]   Win rate: {self.patterns['win_rate']*100:.1f}%")
        self.logger.info(f"[ML]   Avg win: +{self.patterns['avg_win_pnl']:.2f}%")
        self.logger.info(f"[ML]   Avg loss: {self.patterns['avg_loss_pnl']:.2f}%")
    
    async def _learn_optimal_ranges(self, profitable_trades: List[TradeRecord]):
        """Learn optimal parameter ranges from profitable trades"""
        if not profitable_trades:
            return
        
        rsi_values = [t.rsi for t in profitable_trades]
        stoch_values = [t.stoch_rsi for t in profitable_trades]
        score_values = [t.signal_score for t in profitable_trades]
        volume_values = [t.volume_usd for t in profitable_trades]
        change_values = [t.change_percent for t in profitable_trades]
        
        self.patterns["optimal_ranges"] = {
            "rsi_min": max(20, np.percentile(rsi_values, 10)),
            "rsi_max": min(75, np.percentile(rsi_values, 90)),
            "stoch_rsi_max": min(85, np.percentile(stoch_values, 90)),
            "score_min": max(50, np.percentile(score_values, 25)),
            "volume_min": max(50000, np.percentile(volume_values, 25)),
            "change_min": max(0.5, np.percentile(change_values, 10)),
            "change_max": min(20, np.percentile(change_values, 90))
        }
        
        self.logger.debug(f"[ML] Learned optimal ranges: {self.patterns['optimal_ranges']}")
    
    async def _learn_categorical_success(
        self,
        trades: List[TradeRecord],
        field_name: str,
        pattern_key: str
    ):
        """Learn success rates for categorical features"""
        categories = {}
        
        for trade in trades:
            value = getattr(trade, field_name, "unknown")
            if value not in categories:
                categories[value] = {"total": 0, "profitable": 0}
            categories[value]["total"] += 1
            if trade.is_profitable:
                categories[value]["profitable"] += 1
        
        self.patterns[pattern_key] = {
            cat: stats["profitable"] / stats["total"] if stats["total"] > 0 else 0.5
            for cat, stats in categories.items()
        }
    
    async def _learn_hour_patterns(self, trades: List[TradeRecord]):
        """Learn which hours/days are most profitable"""
        hour_stats = {}
        day_stats = {}
        
        for trade in trades:
            h = trade.hour_of_day
            d = trade.day_of_week
            
            if h not in hour_stats:
                hour_stats[h] = {"total": 0, "profitable": 0}
            hour_stats[h]["total"] += 1
            if trade.is_profitable:
                hour_stats[h]["profitable"] += 1
            
            if d not in day_stats:
                day_stats[d] = {"total": 0, "profitable": 0}
            day_stats[d]["total"] += 1
            if trade.is_profitable:
                day_stats[d]["profitable"] += 1
        
        self.patterns["hour_success"] = {
            str(h): stats["profitable"] / stats["total"] if stats["total"] > 0 else 0.5
            for h, stats in hour_stats.items()
        }
        
        self.patterns["day_success"] = {
            str(d): stats["profitable"] / stats["total"] if stats["total"] > 0 else 0.5
            for d, stats in day_stats.items()
        }
    
    async def _learn_feature_weights(self, trades: List[TradeRecord]):
        """Learn feature importance from correlation with profitability"""
        if len(trades) < 20:
            return
        
        # Simple correlation-based weight learning
        features = {
            "score": [t.signal_score / 100 for t in trades],
            "rsi": [1 - abs(t.rsi - 50) / 50 for t in trades],  # Closer to 50 is better
            "stoch_rsi": [1 - t.stoch_rsi / 100 for t in trades],  # Lower is better
            "volume": [min(t.volume_usd / 500000, 1) for t in trades],  # Normalize
            "btc_correlation": [(t.btc_correlation + 1) / 2 for t in trades]  # Normalize -1 to 1
        }
        
        outcomes = [1 if t.is_profitable else 0 for t in trades]
        
        # Calculate simple correlation for each feature
        correlations = {}
        for name, values in features.items():
            if len(set(values)) > 1:  # Has variance
                corr = np.corrcoef(values, outcomes)[0, 1]
                correlations[name] = max(0, corr)  # Only positive correlations
        
        # Normalize weights
        total = sum(correlations.values()) or 1
        self.patterns["weights"] = {
            name: corr / total for name, corr in correlations.items()
        }
        
        self.logger.debug(f"[ML] Learned weights: {self.patterns['weights']}")
    
    # ==================== PREDICTION ====================
    
    def predict_success(
        self,
        signal_type: str = "",
        signal_score: float = 0.0,
        rsi: float = 50.0,
        stoch_rsi: float = 50.0,
        macd_signal: str = "neutral",
        ema_trend: str = "neutral",
        volume_usd: float = 0.0,
        change_percent: float = 0.0,
        btc_correlation: float = 0.0
    ) -> Tuple[bool, float, List[str]]:
        """
        Predict if a trade will be successful
        
        Returns:
            (should_trade, confidence, reasons)
        """
        if not self.is_trained:
            return True, 0.5, ["Model not yet trained"]
        
        score = 0.5  # Base score
        reasons = []
        weights = self.patterns.get("weights", {})
        ranges = self.patterns.get("optimal_ranges", {})
        
        # 1. Signal score component
        if signal_score >= ranges.get("score_min", 60):
            score += 0.1 * weights.get("score", 0.3)
            reasons.append(f"Good score: {signal_score:.0f}")
        else:
            score -= 0.1
            reasons.append(f"Low score: {signal_score:.0f}")
        
        # 2. RSI component
        rsi_min = ranges.get("rsi_min", 30)
        rsi_max = ranges.get("rsi_max", 65)
        if rsi_min <= rsi <= rsi_max:
            score += 0.1 * weights.get("rsi", 0.15)
            reasons.append(f"RSI in optimal range: {rsi:.0f}")
        else:
            score -= 0.05
            reasons.append(f"RSI out of range: {rsi:.0f}")
        
        # 3. Stochastic RSI
        if stoch_rsi <= ranges.get("stoch_rsi_max", 75):
            score += 0.05 * weights.get("stoch_rsi", 0.1)
        else:
            score -= 0.1
            reasons.append(f"StochRSI too high: {stoch_rsi:.0f}")
        
        # 4. MACD success rate
        macd_success = self.patterns.get("macd_success", {}).get(macd_signal, 0.5)
        score += (macd_success - 0.5) * 0.2
        if macd_success > 0.55:
            reasons.append(f"MACD {macd_signal}: {macd_success*100:.0f}% success")
        
        # 5. EMA success rate
        ema_success = self.patterns.get("ema_success", {}).get(ema_trend, 0.5)
        score += (ema_success - 0.5) * 0.2
        if ema_success > 0.55:
            reasons.append(f"EMA {ema_trend}: {ema_success*100:.0f}% success")
        
        # 6. Signal type success rate
        type_success = self.patterns.get("signal_type_success", {}).get(signal_type, 0.5)
        score += (type_success - 0.5) * 0.2
        if type_success > 0.55:
            reasons.append(f"{signal_type}: {type_success*100:.0f}% success")
        
        # 7. Volume component
        if volume_usd >= ranges.get("volume_min", 100000):
            score += 0.05 * weights.get("volume", 0.1)
        
        # 8. Hour/day patterns
        now = datetime.utcnow()
        hour_success = self.patterns.get("hour_success", {}).get(str(now.hour), 0.5)
        day_success = self.patterns.get("day_success", {}).get(str(now.weekday()), 0.5)
        
        if hour_success > 0.55:
            score += 0.05
            reasons.append(f"Good hour: {hour_success*100:.0f}% win rate")
        if day_success > 0.55:
            score += 0.05
        
        # 9. BTC correlation
        if btc_correlation >= 0:
            score += 0.05 * weights.get("btc_correlation", 0.1)
        else:
            score -= 0.1
            reasons.append("Trading against BTC trend")
        
        # Normalize score to 0-1
        confidence = max(0, min(1, score))
        
        # Decision threshold - PLUS STRICT quand modèle bien entraîné
        if self.patterns["total_trades"] >= 100:
            threshold = 0.65  # Très strict si beaucoup de données
        elif self.patterns["total_trades"] >= 50:
            threshold = 0.60  # Strict si assez de données
        else:
            threshold = 0.55  # Modérément strict si peu de données
        
        should_trade = confidence >= threshold
        
        if not should_trade:
            reasons.append(f"ML confidence too low: {confidence*100:.0f}%")
        
        return should_trade, confidence, reasons
    
    def get_ml_boost(
        self,
        signal_type: str,
        macd_signal: str,
        ema_trend: str
    ) -> float:
        """
        Get a score boost/penalty based on learned patterns
        
        Returns a multiplier (0.8 to 1.2)
        """
        if not self.is_trained:
            return 1.0
        
        boost = 1.0
        
        # Signal type boost
        type_success = self.patterns.get("signal_type_success", {}).get(signal_type, 0.5)
        boost += (type_success - 0.5) * 0.2
        
        # MACD boost
        macd_success = self.patterns.get("macd_success", {}).get(macd_signal, 0.5)
        boost += (macd_success - 0.5) * 0.2
        
        # EMA boost
        ema_success = self.patterns.get("ema_success", {}).get(ema_trend, 0.5)
        boost += (ema_success - 0.5) * 0.2
        
        return max(0.8, min(1.2, boost))
    
    # ==================== PERSISTENCE ====================
    
    async def _save_data(self):
        """Save trade records to disk"""
        try:
            filepath = os.path.join(self.DATA_DIR, self.TRADES_FILE)
            data = [t.to_dict() for t in self.trade_records]
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.debug(f"[ML] Saved {len(self.trade_records)} trade records")
        except Exception as e:
            self.logger.error(f"[ML] Failed to save data: {e}")
    
    async def _load_data(self):
        """Load trade records from disk"""
        try:
            filepath = os.path.join(self.DATA_DIR, self.TRADES_FILE)
            
            if not os.path.exists(filepath):
                return
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.trade_records = [TradeRecord.from_dict(d) for d in data]
            self.logger.info(f"[ML] Loaded {len(self.trade_records)} trade records from disk")
            
        except Exception as e:
            self.logger.error(f"[ML] Failed to load data: {e}")
    
    async def _save_patterns(self):
        """Save learned patterns to disk"""
        try:
            filepath = os.path.join(self.DATA_DIR, self.MODEL_FILE)
            
            with open(filepath, 'w') as f:
                json.dump(self.patterns, f, indent=2, default=str)
            
            self.logger.debug("[ML] Saved learned patterns")
        except Exception as e:
            self.logger.error(f"[ML] Failed to save patterns: {e}")
    
    async def _load_patterns(self):
        """Load learned patterns from disk"""
        try:
            filepath = os.path.join(self.DATA_DIR, self.MODEL_FILE)
            
            if not os.path.exists(filepath):
                return
            
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            
            self.patterns.update(loaded)
            self.is_trained = self.patterns.get("total_trades", 0) >= self.MIN_TRADES_FOR_TRAINING
            
            self.logger.info(f"[ML] Loaded patterns (trained on {self.patterns.get('total_trades', 0)} trades)")
            
        except Exception as e:
            self.logger.error(f"[ML] Failed to load patterns: {e}")
    
    # ==================== STATS ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return {
            "total_records": len(self.trade_records),
            "completed_trades": len([t for t in self.trade_records if t.exit_time]),
            "is_trained": self.is_trained,
            "win_rate": f"{self.patterns.get('win_rate', 0) * 100:.1f}%",
            "avg_win": f"+{self.patterns.get('avg_win_pnl', 0):.2f}%",
            "avg_loss": f"{self.patterns.get('avg_loss_pnl', 0):.2f}%",
            "last_trained": self.patterns.get("last_trained"),
            "signal_success_rates": self.patterns.get("signal_type_success", {}),
            "best_hours": {
                h: f"{rate*100:.0f}%" 
                for h, rate in sorted(
                    self.patterns.get("hour_success", {}).items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
            }
        }

