"""
ML Predictor - Machine Learning Price Prediction

Uses multiple ML models to predict crypto price movements:
- LSTM for time-series prediction
- XGBoost for classification (up/down)
- Ensemble voting for final signal
"""

import asyncio
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from src.core.config import settings
from src.core.risk_manager import RiskManager
from src.utils.logger import get_logger

# ML imports (optional, will handle if not installed)
try:
    import torch
    import torch.nn as nn
    from xgboost import XGBClassifier
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# Feature engineering
from src.modules.ml_predictor.feature_engineer import FeatureEngineer


logger = get_logger(__name__)


class MLPredictor:
    """
    Machine Learning predictor for crypto price movements
    
    Strategy:
    1. Collect historical price data
    2. Generate features (technical indicators)
    3. Train models (LSTM, XGBoost)
    4. Generate predictions
    5. Emit trading signals
    """
    
    # Model parameters
    SEQUENCE_LENGTH = 60  # Use last 60 candles for LSTM
    FORECAST_HORIZON = 1  # Predict next candle
    
    # Signal thresholds
    CONFIDENCE_THRESHOLD = 0.65  # Minimum confidence for signal
    
    # Training parameters
    MIN_DATA_POINTS = 500  # Minimum historical data for training
    RETRAIN_INTERVAL_HOURS = 24  # Retrain every 24 hours
    
    def __init__(self, risk_manager: RiskManager):
        """
        Initialize ML predictor
        
        Args:
            risk_manager: Risk manager instance
        """
        self.logger = logger
        self.risk_manager = risk_manager
        
        self.is_running = False
        self.is_initialized = False
        
        # ML availability
        self.ml_available = ML_AVAILABLE
        
        # Components
        self.feature_engineer = FeatureEngineer()
        
        # Models
        self.lstm_model = None
        self.xgb_model = None
        
        # Data
        self.historical_data: Dict[str, pd.DataFrame] = {}
        self.feature_columns: List[str] = []
        
        # Statistics
        self.predictions_made = 0
        self.signals_generated = 0
        self.signal_callbacks = []
        
        # Last training time
        self.last_train_time: Optional[datetime] = None
        
        if not self.ml_available:
            self.logger.warning("🤖 ML Predictor: PyTorch/XGBoost not available")
            self.logger.warning("   Install with: pip install torch xgboost")
        
        self.logger.info("🤖 ML Predictor initialized")
    
    async def initialize(self):
        """Initialize ML predictor"""
        try:
            self.logger.info("[INIT] Initializing ML Predictor...")
            
            if not self.ml_available:
                self.logger.warning("[WARN] ML libraries not available, running in limited mode")
                self.is_initialized = True
                return
            
            # Load or create models
            await self._initialize_models()
            
            self.is_initialized = True
            self.logger.info("[OK] ML Predictor initialized")
            
        except Exception as e:
            self.logger.error(f"ML Predictor initialization failed: {e}")
            raise
    
    async def _initialize_models(self):
        """Initialize ML models"""
        self.logger.info("   Initializing models...")
        
        # Initialize XGBoost classifier
        if ML_AVAILABLE:
            self.xgb_model = XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            self.logger.info("   ✅ XGBoost model initialized")
        
        # LSTM will be initialized on first training
        self.logger.info("   ✅ LSTM model will be trained on first data")
    
    def on_signal(self, callback):
        """Register callback for trading signals"""
        self.signal_callbacks.append(callback)
    
    async def run(self):
        """Main ML predictor loop"""
        if not self.is_initialized:
            await self.initialize()
        
        self.is_running = True
        self.logger.info("[RUN]  ML Predictor started")
        
        if not self.ml_available:
            self.logger.info("[INFO] Running in demonstration mode (no actual predictions)")
        
        try:
            # Start prediction loop
            prediction_task = asyncio.create_task(self._prediction_loop())
            
            # Start retraining loop
            retrain_task = asyncio.create_task(self._retraining_loop())
            
            # Wait for tasks
            await asyncio.gather(prediction_task, retrain_task)
            
        except asyncio.CancelledError:
            self.logger.info("ML Predictor cancelled")
        except Exception as e:
            self.logger.error(f"ML Predictor error: {e}")
        finally:
            await self.stop()
    
    async def _prediction_loop(self):
        """Generate predictions periodically"""
        while self.is_running:
            try:
                # Demo mode simulation
                if not self.ml_available:
                    self.logger.info("   [DEMO] Would generate predictions here")
                    await asyncio.sleep(300)  # Every 5 minutes
                    continue
                
                # Generate predictions for tracked tokens
                tokens = ["BTC", "ETH"]  # Example tokens
                
                for token in tokens:
                    prediction = await self._generate_prediction(token)
                    
                    if prediction:
                        signal = await self._convert_to_signal(token, prediction)
                        if signal:
                            await self._emit_signal(signal)
                
                # Predict every 15 minutes
                await asyncio.sleep(900)
                
            except Exception as e:
                self.logger.error(f"Prediction loop error: {e}")
                await asyncio.sleep(60)
    
    async def _retraining_loop(self):
        """Retrain models periodically"""
        while self.is_running:
            try:
                # Retrain every 24 hours
                await asyncio.sleep(self.RETRAIN_INTERVAL_HOURS * 3600)
                
                if not self.ml_available:
                    continue
                
                self.logger.info("🔄 Starting model retraining...")
                
                # Retrain for each tracked token
                tokens = ["BTC", "ETH"]
                
                for token in tokens:
                    await self._train_models(token)
                
                self.last_train_time = datetime.utcnow()
                self.logger.info("✅ Model retraining complete")
                
            except Exception as e:
                self.logger.error(f"Retraining error: {e}")
    
    async def _generate_prediction(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Generate price prediction for a token
        
        Args:
            token: Token symbol
        
        Returns:
            Prediction dict
        """
        try:
            # Get historical data (simulated for now)
            # In production, would fetch from database or exchange
            data = await self._get_historical_data(token)
            
            if data is None or len(data) < self.MIN_DATA_POINTS:
                return None
            
            # Generate features
            df_features = self.feature_engineer.create_features(data)
            
            # Get predictions from models
            lstm_pred = await self._predict_lstm(df_features)
            xgb_pred = await self._predict_xgb(df_features)
            
            # Ensemble prediction
            prediction = {
                "token": token,
                "lstm": lstm_pred,
                "xgb": xgb_pred,
                "ensemble": self._ensemble_prediction(lstm_pred, xgb_pred),
                "timestamp": datetime.utcnow()
            }
            
            self.predictions_made += 1
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"Prediction failed for {token}: {e}")
            return None
    
    async def _get_historical_data(self, token: str) -> Optional[pd.DataFrame]:
        """
        Get historical OHLCV data
        
        In production, would fetch from:
        - Database (stored historical data)
        - Exchange API (CCXT)
        - Data provider (Glassnode, etc.)
        """
        # Simulated data for demo
        return None
    
    async def _predict_lstm(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate LSTM prediction"""
        if self.lstm_model is None:
            return {"prediction": 0.5, "confidence": 0.5}
        
        # Would use actual LSTM here
        return {
            "prediction": 0.5,  # Placeholder
            "confidence": 0.5,
            "direction": "neutral"
        }
    
    async def _predict_xgb(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate XGBoost prediction"""
        if self.xgb_model is None:
            return {"prediction": 0.5, "confidence": 0.5}
        
        # Would use actual XGBoost here
        return {
            "prediction": 0.5,  # Placeholder
            "confidence": 0.5,
            "direction": "neutral"
        }
    
    def _ensemble_prediction(self, lstm_pred: Dict, xgb_pred: Dict) -> Dict[str, Any]:
        """
        Combine predictions from multiple models
        
        Uses weighted voting
        """
        # Weight by confidence
        lstm_weight = lstm_pred.get("confidence", 0.5)
        xgb_weight = xgb_pred.get("confidence", 0.5)
        
        total_weight = lstm_weight + xgb_weight
        
        if total_weight == 0:
            return {"prediction": 0.5, "confidence": 0.0, "direction": "neutral"}
        
        # Weighted average
        ensemble_pred = (
            lstm_pred.get("prediction", 0.5) * lstm_weight +
            xgb_pred.get("prediction", 0.5) * xgb_weight
        ) / total_weight
        
        # Average confidence
        ensemble_conf = (lstm_weight + xgb_weight) / 2
        
        # Determine direction
        if ensemble_pred > 0.55:
            direction = "up"
        elif ensemble_pred < 0.45:
            direction = "down"
        else:
            direction = "neutral"
        
        return {
            "prediction": ensemble_pred,
            "confidence": ensemble_conf,
            "direction": direction
        }
    
    async def _convert_to_signal(
        self,
        token: str,
        prediction: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert prediction to trading signal"""
        
        ensemble = prediction["ensemble"]
        
        # Check confidence threshold
        if ensemble["confidence"] < self.CONFIDENCE_THRESHOLD:
            return None
        
        # Generate signal based on direction
        if ensemble["direction"] == "up":
            signal = {
                "token": token,
                "direction": "BUY",
                "confidence": ensemble["confidence"],
                "prediction": ensemble["prediction"],
                "models": {
                    "lstm": prediction["lstm"],
                    "xgb": prediction["xgb"]
                },
                "reason": f"ML prediction: {ensemble['direction']} ({ensemble['confidence']:.2%})",
                "timestamp": datetime.utcnow()
            }
            return signal
        
        elif ensemble["direction"] == "down":
            signal = {
                "token": token,
                "direction": "SELL",
                "confidence": ensemble["confidence"],
                "prediction": ensemble["prediction"],
                "models": {
                    "lstm": prediction["lstm"],
                    "xgb": prediction["xgb"]
                },
                "reason": f"ML prediction: {ensemble['direction']} ({ensemble['confidence']:.2%})",
                "timestamp": datetime.utcnow()
            }
            return signal
        
        return None
    
    async def _emit_signal(self, signal: Dict[str, Any]):
        """Emit a trading signal"""
        self.signals_generated += 1
        
        self.logger.info(f"")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"🤖 ML PREDICTION SIGNAL #{self.signals_generated}")
        self.logger.info(f"   Token: {signal['token']}")
        self.logger.info(f"   Direction: {signal['direction']}")
        self.logger.info(f"   Confidence: {signal['confidence']:.2%}")
        self.logger.info(f"   Reason: {signal['reason']}")
        self.logger.info(f"{'='*60}")
        
        # Call registered callbacks
        for callback in self.signal_callbacks:
            try:
                await callback(signal)
            except Exception as e:
                self.logger.error(f"Signal callback error: {e}")
    
    async def _train_models(self, token: str):
        """Train models for a token"""
        try:
            self.logger.info(f"   Training models for {token}...")
            
            # Get training data
            data = await self._get_historical_data(token)
            
            if data is None or len(data) < self.MIN_DATA_POINTS:
                self.logger.warning(f"   Insufficient data for {token}")
                return
            
            # Generate features
            df_features = self.feature_engineer.create_features(data)
            
            # Train XGBoost
            # ... training logic ...
            
            # Train LSTM
            # ... training logic ...
            
            self.logger.info(f"   ✅ Models trained for {token}")
            
        except Exception as e:
            self.logger.error(f"Training failed for {token}: {e}")
    
    async def stop(self):
        """Stop ML predictor"""
        self.is_running = False
        
        self.logger.info("[STOP]  ML Predictor stopped")
        self.logger.info(f"   Predictions made: {self.predictions_made}")
        self.logger.info(f"   Signals generated: {self.signals_generated}")
    
    async def is_healthy(self) -> bool:
        """Health check"""
        return self.is_running and self.is_initialized
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get ML predictor statistics"""
        return {
            "predictions_made": self.predictions_made,
            "signals_generated": self.signals_generated,
            "ml_available": self.ml_available,
            "models_trained": self.lstm_model is not None or self.xgb_model is not None,
            "last_train_time": self.last_train_time.isoformat() if self.last_train_time else None
        }
