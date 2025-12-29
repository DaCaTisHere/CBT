"""
SQLAlchemy Models for Cryptobot Ultimate

Database models for storing trading data, positions, and analytics.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Numeric, 
    ForeignKey, Text, CheckConstraint, Index, Enum as SQLEnum, JSON
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid
import enum
import os


Base = declarative_base()


def _is_sqlite():
    """Check if using SQLite"""
    db_url = os.getenv("DATABASE_URL", "sqlite")
    return "sqlite" in db_url


# Use String(36) for SQLite (UUID not supported), UUID for PostgreSQL  
def get_uuid_column(**kwargs):
    """Get appropriate UUID column type"""
    if _is_sqlite():
        return Column(String(36), default=lambda: str(uuid.uuid4()), **kwargs)
    else:
        from sqlalchemy.dialects.postgresql import UUID
        return Column(UUID(as_uuid=True), default=uuid.uuid4, **kwargs)


# Use JSON for SQLite, JSONB for PostgreSQL
def get_json_type():
    """Get appropriate JSON type based on database"""
    if _is_sqlite():
        return JSON
    else:
        return JSONB


# ==========================================
# Enums
# ==========================================

class TradeSide(str, enum.Enum):
    """Trade side: BUY or SELL"""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    """Trade execution status"""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, enum.Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class EventSeverity(str, enum.Enum):
    """System event severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ==========================================
# Core Models
# ==========================================

class Token(Base):
    """Token information"""
    __tablename__ = "tokens"
    __table_args__ = (
        Index('idx_tokens_address', 'address'),
        Index('idx_tokens_chain', 'chain'),
        Index('idx_tokens_symbol', 'symbol'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    address = Column(String(66), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(100))
    chain = Column(String(20), nullable=False)
    decimals = Column(Integer, nullable=False, default=18)
    is_verified = Column(Boolean, default=False)
    is_scam = Column(Boolean, default=False)
    safety_score = Column(Integer)  # 0-100
    token_metadata = Column(get_json_type())  # Additional token info
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    pairs_as_token0 = relationship("Pair", foreign_keys="[Pair.token0_id]", back_populates="token0")
    pairs_as_token1 = relationship("Pair", foreign_keys="[Pair.token1_id]", back_populates="token1")
    trades = relationship("Trade", back_populates="token")
    positions = relationship("Position", back_populates="token")
    ohlcv_data = relationship("OHLCV", back_populates="token")

    def __repr__(self):
        return f"<Token {self.symbol} ({self.chain})>"


class Pair(Base):
    """DEX trading pair"""
    __tablename__ = "pairs"
    __table_args__ = (
        Index('idx_pairs_dex', 'dex'),
        Index('idx_pairs_chain', 'chain'),
        Index('idx_pairs_tokens', 'token0_id', 'token1_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    address = Column(String(66), nullable=False)
    token0_id = Column(String(36), ForeignKey('tokens.id'))
    token1_id = Column(String(36), ForeignKey('tokens.id'))
    dex = Column(String(50), nullable=False)  # Uniswap, Sushiswap, etc.
    chain = Column(String(20), nullable=False)
    liquidity_usd = Column(Numeric(20, 2))
    volume_24h = Column(Numeric(20, 2))
    pair_metadata = Column(get_json_type())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    token0 = relationship("Token", foreign_keys=[token0_id], back_populates="pairs_as_token0")
    token1 = relationship("Token", foreign_keys=[token1_id], back_populates="pairs_as_token1")
    trades = relationship("Trade", back_populates="pair")
    ohlcv_data = relationship("OHLCV", back_populates="pair")

    def __repr__(self):
        return f"<Pair {self.dex} on {self.chain}>"


class Trade(Base):
    """Individual trade execution"""
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name='check_trade_side'),
        CheckConstraint("status IN ('PENDING', 'SUCCESS', 'FAILED', 'CANCELLED')", name='check_trade_status'),
        Index('idx_trades_strategy', 'strategy'),
        Index('idx_trades_status', 'status'),
        Index('idx_trades_executed_at', 'executed_at'),
        Index('idx_trades_token_id', 'token_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy = Column(String(50), nullable=False)  # sniper, news_trader, etc.
    token_id = Column(String(36), ForeignKey('tokens.id'))
    pair_id = Column(String(36), ForeignKey('pairs.id'))
    side = Column(String(10), nullable=False)
    amount = Column(Numeric(30, 18), nullable=False)
    price = Column(Numeric(30, 18), nullable=False)
    value_usd = Column(Numeric(20, 2))
    gas_used = Column(Numeric(20, 8))
    gas_price_gwei = Column(Numeric(20, 8))
    tx_hash = Column(String(66))
    status = Column(String(20), nullable=False)
    error_message = Column(Text)
    trade_metadata = Column(get_json_type())
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    token = relationship("Token", back_populates="trades")
    pair = relationship("Pair", back_populates="trades")
    position_entries = relationship("Position", foreign_keys="[Position.entry_trade_id]", back_populates="entry_trade")
    position_exits = relationship("Position", foreign_keys="[Position.exit_trade_id]", back_populates="exit_trade")

    def __repr__(self):
        return f"<Trade {self.side} {self.strategy} - {self.status}>"


class Position(Base):
    """Trading position (open or closed)"""
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'LIQUIDATED')", name='check_position_status'),
        Index('idx_positions_strategy', 'strategy'),
        Index('idx_positions_status', 'status'),
        Index('idx_positions_token_id', 'token_id'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy = Column(String(50), nullable=False)
    token_id = Column(String(36), ForeignKey('tokens.id'))
    entry_trade_id = Column(String(36), ForeignKey('trades.id'))
    exit_trade_id = Column(String(36), ForeignKey('trades.id'), nullable=True)
    entry_price = Column(Numeric(30, 18), nullable=False)
    exit_price = Column(Numeric(30, 18))
    amount = Column(Numeric(30, 18), nullable=False)
    status = Column(String(20), nullable=False)
    pnl_usd = Column(Numeric(20, 2))
    pnl_percent = Column(Numeric(10, 4))
    stop_loss_price = Column(Numeric(30, 18))
    take_profit_price = Column(Numeric(30, 18))
    position_metadata = Column(get_json_type())
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    token = relationship("Token", back_populates="positions")
    entry_trade = relationship("Trade", foreign_keys=[entry_trade_id], back_populates="position_entries")
    exit_trade = relationship("Trade", foreign_keys=[exit_trade_id], back_populates="position_exits")

    def __repr__(self):
        return f"<Position {self.strategy} - {self.status}>"


class OHLCV(Base):
    """Price candlestick data (TimescaleDB hypertable)"""
    __tablename__ = "ohlcv"
    __table_args__ = (
        Index('idx_ohlcv_token_id', 'token_id'),
        Index('idx_ohlcv_pair_id', 'pair_id'),
        Index('idx_ohlcv_timeframe', 'timeframe'),
    )

    time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    token_id = Column(String(36), ForeignKey('tokens.id'), primary_key=True)
    pair_id = Column(String(36), ForeignKey('pairs.id'))
    timeframe = Column(String(10), primary_key=True, nullable=False)  # 1m, 5m, 1h, etc.
    open = Column(Numeric(30, 18), nullable=False)
    high = Column(Numeric(30, 18), nullable=False)
    low = Column(Numeric(30, 18), nullable=False)
    close = Column(Numeric(30, 18), nullable=False)
    volume = Column(Numeric(30, 18), nullable=False)

    # Relationships
    token = relationship("Token", back_populates="ohlcv_data")
    pair = relationship("Pair", back_populates="ohlcv_data")

    def __repr__(self):
        return f"<OHLCV {self.timeframe} at {self.time}>"


# ==========================================
# Analytics Models
# ==========================================

class DailyStats(Base):
    """Daily performance statistics per strategy"""
    __tablename__ = "daily_stats"
    __table_args__ = (
        Index('idx_daily_stats_strategy', 'strategy'),
        Index('idx_daily_stats_date', 'date'),
    )

    date = Column(DateTime(timezone=True), primary_key=True)
    strategy = Column(String(50), primary_key=True)
    total_trades = Column(Integer, default=0)
    profitable_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Numeric(5, 2))
    total_pnl_usd = Column(Numeric(20, 2), default=0)
    total_fees_usd = Column(Numeric(20, 2), default=0)
    net_pnl_usd = Column(Numeric(20, 2), default=0)
    avg_profit = Column(Numeric(20, 2))
    avg_loss = Column(Numeric(20, 2))
    largest_win = Column(Numeric(20, 2))
    largest_loss = Column(Numeric(20, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DailyStats {self.strategy} on {self.date}>"


# ==========================================
# System Models
# ==========================================

class SystemEvent(Base):
    """System events and logs"""
    __tablename__ = "system_events"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')", name='check_event_severity'),
        Index('idx_system_events_type', 'event_type'),
        Index('idx_system_events_severity', 'severity'),
        Index('idx_system_events_created_at', 'created_at'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    event_metadata = Column(get_json_type())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SystemEvent {self.event_type} - {self.severity}>"
