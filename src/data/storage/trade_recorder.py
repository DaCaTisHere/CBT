"""
Trade Recorder - Writes all trades and positions to PostgreSQL (Supabase).

Fire-and-forget: errors are logged but never block trading.
This ensures every trade is persisted in the database for analytics.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

_db_available = False


async def _get_session():
    """Get a DB session, returns None if DB is unavailable."""
    global _db_available
    try:
        from src.data.storage.database import get_db_session
        return get_db_session()
    except Exception as e:
        if _db_available:
            logger.warning(f"[DB] Database unavailable: {e}")
            _db_available = False
        return None


async def init_recorder():
    """Test DB connection and mark as available."""
    global _db_available
    try:
        from src.data.storage.database import test_connection
        _db_available = await test_connection()
        if _db_available:
            logger.info("[DB] Trade recorder connected to PostgreSQL")
        else:
            logger.warning("[DB] Trade recorder: DB connection failed, trades will only be in JSON")
    except Exception as e:
        logger.warning(f"[DB] Trade recorder init failed: {e}")
        _db_available = False


async def record_trade(
    strategy: str,
    side: str,
    symbol: str,
    chain: str,
    amount_usd: float,
    price: float,
    status: str = "SUCCESS",
    tx_hash: Optional[str] = None,
    pnl_usd: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    is_simulation: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Record a trade to PostgreSQL. Fire-and-forget.
    
    Called from safety_manager.record_sell(), dex_trader, grid_trader.
    """
    if not _db_available:
        return

    try:
        from src.data.storage.database import get_db_session
        from src.data.storage.models import Trade

        trade_meta = {
            "is_simulation": is_simulation,
            "chain": chain,
        }
        if pnl_usd is not None:
            trade_meta["pnl_usd"] = pnl_usd
        if pnl_pct is not None:
            trade_meta["pnl_pct"] = pnl_pct
        if metadata:
            trade_meta.update(metadata)

        async with get_db_session() as session:
            trade = Trade(
                strategy=strategy,
                side=side,
                amount=price,
                price=price,
                value_usd=amount_usd,
                tx_hash=tx_hash,
                status=status,
                trade_metadata=trade_meta,
            )
            session.add(trade)

        logger.debug(f"[DB] Trade recorded: {side} {symbol} ${amount_usd:.2f} ({strategy})")

    except Exception as e:
        logger.warning(f"[DB] Failed to record trade: {e}")


async def record_system_event(
    event_type: str,
    severity: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Record a system event to PostgreSQL."""
    if not _db_available:
        return

    try:
        from src.data.storage.database import get_db_session
        from src.data.storage.models import SystemEvent

        async with get_db_session() as session:
            event = SystemEvent(
                event_type=event_type,
                severity=severity,
                message=message,
                event_metadata=metadata or {},
            )
            session.add(event)

    except Exception as e:
        logger.warning(f"[DB] Failed to record event: {e}")


async def record_daily_stats(
    strategy: str,
    total_trades: int,
    profitable_trades: int,
    losing_trades: int,
    total_pnl_usd: float,
    win_rate: float,
):
    """Record daily stats snapshot to PostgreSQL."""
    if not _db_available:
        return

    try:
        from src.data.storage.database import get_db_session
        from src.data.storage.models import DailyStats
        from decimal import Decimal

        async with get_db_session() as session:
            stats = DailyStats(
                date=datetime.now(timezone.utc),
                strategy=strategy,
                total_trades=total_trades,
                profitable_trades=profitable_trades,
                losing_trades=losing_trades,
                win_rate=Decimal(str(round(win_rate, 2))),
                total_pnl_usd=Decimal(str(round(total_pnl_usd, 2))),
                net_pnl_usd=Decimal(str(round(total_pnl_usd, 2))),
            )
            session.add(stats)

    except Exception as e:
        logger.warning(f"[DB] Failed to record daily stats: {e}")


def fire_and_forget(coro):
    """Schedule a coroutine without waiting for it."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass
