"""
Database Models using SQLAlchemy ORM
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, Enum
from sqlalchemy.sql import func
from datetime import datetime
import enum

from src.data.storage.database import Base


class TradeStatus(str, enum.Enum):
    """Trade status enum"""
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradeSide(str, enum.Enum):
    """Trade side enum"""
    LONG = "long"
    SHORT = "short"


class Trade(Base):
    """Trade model"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(Enum(TradeSide), nullable=False)
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.PENDING)
    
    # Prices
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # Amounts
    amount = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    
    # Fees
    entry_fee = Column(Float, default=0.0)
    exit_fee = Column(Float, default=0.0)
    
    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Metadata
    metadata_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)


class Position(Base):
    """Current open position"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(String(100), unique=True, nullable=False, index=True)
    strategy = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(Enum(TradeSide), nullable=False)
    
    amount = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    opened_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Portfolio(Base):
    """Portfolio snapshot"""
    __tablename__ = "portfolio"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    total_capital = Column(Float, nullable=False)
    available_capital = Column(Float, nullable=False)
    in_positions = Column(Float, default=0.0)
    
    total_pnl = Column(Float, default=0.0)
    daily_pnl = Column(Float, default=0.0)
    
    num_open_positions = Column(Integer, default=0)
    num_trades_today = Column(Integer, default=0)


class StrategyMetrics(Base):
    """Per-strategy performance metrics"""
    __tablename__ = "strategy_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String(50), nullable=False, index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    
    total_pnl = Column(Float, default=0.0)
    avg_win = Column(Float, default=0.0)
    avg_loss = Column(Float, default=0.0)
    
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)

