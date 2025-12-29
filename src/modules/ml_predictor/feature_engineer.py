"""
Feature Engineering for ML Models

Generates technical indicators and features for price prediction.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from src.utils.logger import get_logger


logger = get_logger(__name__)


class FeatureEngineer:
    """
    Feature engineering for crypto price prediction
    
    Generates:
    - Technical indicators (RSI, MACD, Bollinger Bands, etc.)
    - Price-based features (returns, volatility)
    - Volume features
    - Time-based features
    - On-chain metrics (if available)
    """
    
    def __init__(self):
        self.logger = logger
        self.logger.info("[FEATURES] Feature Engineer initialized")
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create all features from OHLCV data
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume, timestamp
        
        Returns:
            DataFrame with added features
        """
        df = df.copy()
        
        # Price-based features
        df = self._add_price_features(df)
        
        # Technical indicators
        df = self._add_technical_indicators(df)
        
        # Volume features
        df = self._add_volume_features(df)
        
        # Time features
        df = self._add_time_features(df)
        
        # Lag features
        df = self._add_lag_features(df)
        
        # Drop NaN rows
        df = df.dropna()
        
        self.logger.info(f"[FEATURES] Created {len(df.columns)} features")
        
        return df
    
    def _add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features"""
        
        # Returns
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        
        # Price changes
        df['price_change'] = df['close'] - df['open']
        df['price_change_pct'] = (df['close'] - df['open']) / df['open']
        
        # High-Low range
        df['hl_range'] = df['high'] - df['low']
        df['hl_range_pct'] = (df['high'] - df['low']) / df['low']
        
        # Close vs Open/High/Low
        df['close_vs_high'] = (df['close'] - df['high']) / df['high']
        df['close_vs_low'] = (df['close'] - df['low']) / df['low']
        df['close_vs_open'] = (df['close'] - df['open']) / df['open']
        
        # Rolling statistics
        for window in [5, 10, 20, 50]:
            df[f'close_sma_{window}'] = df['close'].rolling(window).mean()
            df[f'close_std_{window}'] = df['close'].rolling(window).std()
            df[f'returns_mean_{window}'] = df['returns'].rolling(window).mean()
            df[f'returns_std_{window}'] = df['returns'].rolling(window).std()
        
        return df
    
    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators"""
        
        # RSI (Relative Strength Index)
        for period in [14, 21]:
            df[f'rsi_{period}'] = self._calculate_rsi(df['close'], period)
        
        # MACD (Moving Average Convergence Divergence)
        df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])
        
        # Bollinger Bands
        for window in [20]:
            sma = df['close'].rolling(window).mean()
            std = df['close'].rolling(window).std()
            df[f'bb_upper_{window}'] = sma + (2 * std)
            df[f'bb_lower_{window}'] = sma - (2 * std)
            df[f'bb_width_{window}'] = (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}']) / sma
            df[f'bb_position_{window}'] = (df['close'] - df[f'bb_lower_{window}']) / (df[f'bb_upper_{window}'] - df[f'bb_lower_{window}'])
        
        # ATR (Average True Range)
        df['atr_14'] = self._calculate_atr(df, 14)
        
        # Stochastic Oscillator
        df['stoch_k'], df['stoch_d'] = self._calculate_stochastic(df)
        
        # EMA (Exponential Moving Average)
        for span in [12, 26, 50, 200]:
            df[f'ema_{span}'] = df['close'].ewm(span=span, adjust=False).mean()
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(self, prices: pd.Series, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        return macd, macd_signal, macd_hist
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean()
        
        return atr
    
    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
        """Calculate Stochastic Oscillator"""
        low_min = df['low'].rolling(k_period).min()
        high_max = df['high'].rolling(k_period).max()
        
        stoch_k = 100 * (df['close'] - low_min) / (high_max - low_min)
        stoch_d = stoch_k.rolling(d_period).mean()
        
        return stoch_k, stoch_d
    
    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume-based features"""
        
        # Volume change
        df['volume_change'] = df['volume'].pct_change()
        
        # Volume moving averages
        for window in [5, 10, 20]:
            df[f'volume_sma_{window}'] = df['volume'].rolling(window).mean()
            df[f'volume_ratio_{window}'] = df['volume'] / df[f'volume_sma_{window}']
        
        # On-Balance Volume (OBV)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        
        # Volume-Price Trend
        df['vpt'] = (df['volume'] * df['returns']).cumsum()
        
        return df
    
    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features"""
        
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            df['day_of_week'] = pd.to_datetime(df['timestamp']).dt.dayofweek
            df['day_of_month'] = pd.to_datetime(df['timestamp']).dt.day
            df['month'] = pd.to_datetime(df['timestamp']).dt.month
            
            # Cyclical encoding
            df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
            df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
            df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
            df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        
        return df
    
    def _add_lag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add lagged features"""
        
        # Lagged prices
        for lag in [1, 2, 3, 5, 10]:
            df[f'close_lag_{lag}'] = df['close'].shift(lag)
            df[f'returns_lag_{lag}'] = df['returns'].shift(lag)
            df[f'volume_lag_{lag}'] = df['volume'].shift(lag)
        
        return df
    
    def get_feature_names(self, df: pd.DataFrame) -> List[str]:
        """Get list of feature column names"""
        exclude = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        features = [col for col in df.columns if col not in exclude]
        return features
    
    def prepare_sequences(
        self,
        df: pd.DataFrame,
        feature_columns: List[str],
        target_column: str,
        sequence_length: int = 60,
        forecast_horizon: int = 1
    ) -> tuple:
        """
        Prepare sequences for LSTM training
        
        Args:
            df: DataFrame with features
            feature_columns: List of feature column names
            target_column: Name of target column
            sequence_length: Length of input sequences
            forecast_horizon: How many steps ahead to predict
        
        Returns:
            X, y arrays
        """
        X, y = [], []
        
        data = df[feature_columns].values
        targets = df[target_column].values
        
        for i in range(len(data) - sequence_length - forecast_horizon + 1):
            X.append(data[i:i + sequence_length])
            y.append(targets[i + sequence_length + forecast_horizon - 1])
        
        return np.array(X), np.array(y)

