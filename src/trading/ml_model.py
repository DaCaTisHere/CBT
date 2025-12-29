"""
Machine Learning Model for Trading Decisions

A real ML model that learns from historical listing data to predict
which new listings are likely to be profitable.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Prediction:
    """ML model prediction"""
    symbol: str
    should_buy: bool
    confidence: float
    predicted_return: float
    risk_level: str  # low, medium, high
    reasoning: List[str]


class TradingMLModel:
    """
    Machine Learning model for listing trading decisions
    
    Uses historical patterns to predict:
    1. Should we buy this listing?
    2. What's the expected return?
    3. What's the risk level?
    """
    
    def __init__(self):
        self.logger = logger
        self.model_dir = "data/models"
        os.makedirs(self.model_dir, exist_ok=True)
        
        # Learned patterns from training
        self.patterns: Dict[str, Any] = {
            "exchange_success_rate": {},
            "token_type_success_rate": {},
            "volume_threshold": 0,
            "sentiment_threshold": 0.5,
            "avg_profitable_return": 0,
            "total_samples": 0,
            "profitable_samples": 0
        }
        
        # Feature weights (learned from data)
        self.weights = {
            "exchange_binance": 0.6,
            "exchange_coinbase": 0.5,
            "high_volume": 0.3,
            "high_sentiment": 0.4,
            "meme_token": 0.2,
            "defi_token": 0.3,
            "layer1_token": 0.4
        }
        
        self.is_trained = False
        
    async def initialize(self):
        """Initialize model"""
        await self._load_model()
        self.logger.info(f"[ML] Model initialized (trained: {self.is_trained})")
        
    async def train(self, training_data: List[Dict]) -> Dict[str, float]:
        """
        Train the model on historical listing data
        
        Args:
            training_data: List of historical listing features
            
        Returns:
            Training metrics
        """
        if not training_data:
            self.logger.warning("[ML] No training data provided")
            return {}
        
        self.logger.info(f"[ML] Training on {len(training_data)} samples...")
        
        # Calculate exchange success rates
        exchange_stats = {}
        for item in training_data:
            exchange = item.get("exchange", "unknown")
            if exchange not in exchange_stats:
                exchange_stats[exchange] = {"total": 0, "profitable": 0}
            exchange_stats[exchange]["total"] += 1
            if item.get("is_profitable", False):
                exchange_stats[exchange]["profitable"] += 1
        
        for exchange, stats in exchange_stats.items():
            if stats["total"] > 0:
                self.patterns["exchange_success_rate"][exchange] = (
                    stats["profitable"] / stats["total"]
                )
        
        # Calculate profit categories
        profit_categories = {}
        for item in training_data:
            cat = item.get("profit_category", "unknown")
            profit_categories[cat] = profit_categories.get(cat, 0) + 1
        
        # Calculate volume threshold
        volumes = [item.get("volume_24h", 0) for item in training_data if item.get("is_profitable")]
        if volumes:
            self.patterns["volume_threshold"] = np.percentile(volumes, 25)
        
        # Calculate sentiment threshold
        sentiments = [item.get("sentiment_score", 0.5) for item in training_data if item.get("is_profitable")]
        if sentiments:
            self.patterns["sentiment_threshold"] = np.mean(sentiments) - np.std(sentiments)
        
        # Calculate average returns
        profitable_returns = [
            item.get("max_return_24h", 0) 
            for item in training_data 
            if item.get("is_profitable")
        ]
        if profitable_returns:
            self.patterns["avg_profitable_return"] = np.mean(profitable_returns)
        
        # Update weights based on correlation analysis
        self._update_weights(training_data)
        
        # Store training stats
        self.patterns["total_samples"] = len(training_data)
        self.patterns["profitable_samples"] = sum(1 for item in training_data if item.get("is_profitable"))
        self.patterns["profit_categories"] = profit_categories
        self.patterns["trained_at"] = datetime.utcnow().isoformat()
        
        self.is_trained = True
        
        # Save model
        await self._save_model()
        
        # Calculate metrics
        metrics = {
            "samples": len(training_data),
            "profitable_rate": self.patterns["profitable_samples"] / len(training_data) * 100,
            "avg_return": self.patterns["avg_profitable_return"],
            "exchanges": len(self.patterns["exchange_success_rate"])
        }
        
        self.logger.info(f"[ML] Training complete!")
        self.logger.info(f"[ML]   Samples: {metrics['samples']}")
        self.logger.info(f"[ML]   Profitable rate: {metrics['profitable_rate']:.1f}%")
        self.logger.info(f"[ML]   Avg return: {metrics['avg_return']:.1f}%")
        
        return metrics
    
    def _update_weights(self, training_data: List[Dict]):
        """Update feature weights based on correlation with profitability"""
        
        # Exchange weight
        for exchange in ["binance", "coinbase"]:
            exchange_items = [
                item for item in training_data 
                if item.get("exchange") == exchange
            ]
            if exchange_items:
                success_rate = sum(
                    1 for item in exchange_items if item.get("is_profitable")
                ) / len(exchange_items)
                self.weights[f"exchange_{exchange}"] = success_rate
        
        # Volume correlation
        high_vol_items = [
            item for item in training_data 
            if item.get("volume_24h", 0) > self.patterns.get("volume_threshold", 0)
        ]
        if high_vol_items:
            vol_success = sum(
                1 for item in high_vol_items if item.get("is_profitable")
            ) / len(high_vol_items)
            self.weights["high_volume"] = vol_success
        
        # Sentiment correlation
        high_sent_items = [
            item for item in training_data 
            if item.get("sentiment_score", 0) > 0.6
        ]
        if high_sent_items:
            sent_success = sum(
                1 for item in high_sent_items if item.get("is_profitable")
            ) / len(high_sent_items)
            self.weights["high_sentiment"] = sent_success
    
    def predict(
        self, 
        symbol: str,
        exchange: str,
        volume: float = 0,
        sentiment: float = 0.5,
        market_cap: float = 0,
        token_type: str = "unknown"
    ) -> Prediction:
        """
        Predict if a new listing should be traded
        
        Args:
            symbol: Token symbol
            exchange: Exchange name
            volume: 24h volume if known
            sentiment: Sentiment score (0-1)
            market_cap: Market cap if known
            token_type: Type of token (meme, defi, layer1, etc)
            
        Returns:
            Prediction with buy signal and confidence
        """
        reasoning = []
        score = 0.5  # Base score
        
        # Exchange factor
        exchange_rate = self.patterns.get("exchange_success_rate", {}).get(
            exchange.lower(), 0.5
        )
        score += (exchange_rate - 0.5) * self.weights.get(f"exchange_{exchange.lower()}", 0.5)
        
        if exchange_rate > 0.6:
            reasoning.append(f"{exchange} has {exchange_rate*100:.0f}% success rate")
        
        # Volume factor
        vol_threshold = self.patterns.get("volume_threshold", 1000000)
        if volume > vol_threshold:
            score += 0.1 * self.weights.get("high_volume", 0.3)
            reasoning.append(f"Volume ${volume:,.0f} above threshold")
        
        # Sentiment factor
        sent_threshold = self.patterns.get("sentiment_threshold", 0.5)
        if sentiment > sent_threshold:
            score += 0.15 * self.weights.get("high_sentiment", 0.4)
            reasoning.append(f"Sentiment {sentiment:.0%} is positive")
        elif sentiment < 0.3:
            score -= 0.2
            reasoning.append(f"Low sentiment {sentiment:.0%} is risky")
        
        # Token type factor
        type_weight = self.weights.get(f"{token_type}_token", 0.3)
        score += (type_weight - 0.3) * 0.5
        
        # Market cap factor (smaller = higher potential but riskier)
        if market_cap > 0:
            if market_cap < 10_000_000:
                score += 0.1
                reasoning.append("Low cap = high potential")
            elif market_cap > 1_000_000_000:
                score -= 0.1
                reasoning.append("Large cap = lower upside")
        
        # Determine risk level
        if score > 0.7:
            risk_level = "low"
        elif score > 0.5:
            risk_level = "medium"
        else:
            risk_level = "high"
        
        # Calculate expected return based on historical data
        avg_return = self.patterns.get("avg_profitable_return", 50)
        predicted_return = avg_return * score
        
        # Final decision
        should_buy = score >= 0.55 and len(reasoning) >= 2
        confidence = min(score, 0.95)
        
        if not reasoning:
            reasoning.append("Insufficient data for analysis")
        
        return Prediction(
            symbol=symbol,
            should_buy=should_buy,
            confidence=confidence,
            predicted_return=predicted_return,
            risk_level=risk_level,
            reasoning=reasoning
        )
    
    async def _save_model(self):
        """Save trained model to disk"""
        try:
            model_file = f"{self.model_dir}/trading_model.json"
            
            save_data = {
                "patterns": self.patterns,
                "weights": self.weights,
                "is_trained": self.is_trained,
                "saved_at": datetime.utcnow().isoformat()
            }
            
            with open(model_file, "w") as f:
                json.dump(save_data, f, indent=2, default=str)
            
            self.logger.info("[ML] Model saved to disk")
            
        except Exception as e:
            self.logger.error(f"[ML] Failed to save model: {e}")
    
    async def _load_model(self):
        """Load trained model from disk"""
        try:
            model_file = f"{self.model_dir}/trading_model.json"
            
            if not os.path.exists(model_file):
                return
            
            with open(model_file, "r") as f:
                data = json.load(f)
            
            self.patterns = data.get("patterns", self.patterns)
            self.weights = data.get("weights", self.weights)
            self.is_trained = data.get("is_trained", False)
            
            self.logger.info(f"[ML] Loaded model from {data.get('saved_at', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"[ML] Failed to load model: {e}")
    
    def get_model_info(self) -> Dict:
        """Get model information"""
        return {
            "is_trained": self.is_trained,
            "total_samples": self.patterns.get("total_samples", 0),
            "profitable_rate": (
                self.patterns.get("profitable_samples", 0) / 
                max(self.patterns.get("total_samples", 1), 1) * 100
            ),
            "avg_return": self.patterns.get("avg_profitable_return", 0),
            "exchange_success_rates": self.patterns.get("exchange_success_rate", {}),
            "trained_at": self.patterns.get("trained_at")
        }

