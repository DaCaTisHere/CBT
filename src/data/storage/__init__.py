"""
Data storage package

Provides trade recording via Supabase REST API.
"""

from src.data.storage.trade_recorder import (
    init_recorder,
    record_trade,
    record_system_event,
    record_daily_stats,
    fire_and_forget,
)

__all__ = [
    "init_recorder",
    "record_trade",
    "record_system_event",
    "record_daily_stats",
    "fire_and_forget",
]
