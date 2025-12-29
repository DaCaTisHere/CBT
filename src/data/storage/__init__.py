"""
Data storage package

Exports database models and connection utilities.
"""

from src.data.storage.models import (
    Base,
    Token,
    Pair,
    Trade,
    Position,
    OHLCV,
    DailyStats,
    SystemEvent,
    TradeSide,
    TradeStatus,
    PositionStatus,
    EventSeverity,
)

from src.data.storage.database import (
    get_engine,
    get_db_session,
    init_database,
    close_database,
    test_connection,
    create_token,
    create_trade,
    create_position,
)


__all__ = [
    # Models
    "Base",
    "Token",
    "Pair",
    "Trade",
    "Position",
    "OHLCV",
    "DailyStats",
    "SystemEvent",
    # Enums
    "TradeSide",
    "TradeStatus",
    "PositionStatus",
    "EventSeverity",
    # Database functions
    "get_engine",
    "get_db_session",
    "init_database",
    "close_database",
    "test_connection",
    "create_token",
    "create_trade",
    "create_position",
]
