"""
Trade Recorder - Writes trades, events and stats to Supabase via REST API.

Fire-and-forget: errors are logged but never block trading.
Uses PostgREST (Supabase REST API) instead of direct PostgreSQL.
"""

import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_available = False
_base_url: Optional[str] = None
_headers: Optional[Dict[str, str]] = None


def _setup():
    global _base_url, _headers, _available
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    if not url or not key:
        return False
    _base_url = f"{url.rstrip('/')}/rest/v1"
    _headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    return True


async def init_recorder():
    """Test Supabase REST connection."""
    global _available
    try:
        if not _setup():
            logger.warning("[DB] SUPABASE_URL or SUPABASE_KEY not set - trade recording disabled")
            return

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_base_url}/trades?select=id&limit=1",
                headers=_headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    _available = True
                    logger.info("[DB] Trade recorder connected to Supabase (REST API)")
                else:
                    body = await resp.text()
                    logger.warning(f"[DB] Supabase REST test failed ({resp.status}): {body[:200]}")
    except Exception as e:
        logger.warning(f"[DB] Trade recorder init failed: {e}")


async def _post(table: str, data: dict):
    """POST a row to a Supabase table. Fire-and-forget."""
    if not _available:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_base_url}/{table}",
                headers=_headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(f"[DB] Insert into {table} failed ({resp.status}): {body[:200]}")
    except Exception as e:
        logger.warning(f"[DB] Failed to write to {table}: {e}")


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
    """Record a trade to Supabase. Fire-and-forget."""
    row = {
        "strategy": strategy,
        "side": side,
        "symbol": symbol,
        "chain": chain,
        "amount": price,
        "price": price,
        "value_usd": amount_usd,
        "status": status,
        "is_simulation": is_simulation,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if tx_hash:
        row["tx_hash"] = tx_hash
    if pnl_usd is not None:
        row["pnl_usd"] = round(pnl_usd, 4)
    if pnl_pct is not None:
        row["pnl_pct"] = round(pnl_pct, 4)

    trade_meta = {"is_simulation": is_simulation, "chain": chain}
    if metadata:
        trade_meta.update(metadata)
    row["trade_metadata"] = trade_meta

    await _post("trades", row)
    logger.debug(f"[DB] Trade recorded: {side} {symbol} ${amount_usd:.2f} ({strategy})")


async def record_system_event(
    event_type: str,
    severity: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Record a system event to Supabase."""
    row = {
        "event_type": event_type,
        "severity": severity,
        "message": message[:2000],
        "event_metadata": metadata or {},
    }
    await _post("system_events", row)


async def record_daily_stats(
    strategy: str,
    total_trades: int,
    profitable_trades: int,
    losing_trades: int,
    total_pnl_usd: float,
    win_rate: float,
):
    """Record daily stats snapshot to Supabase."""
    row = {
        "date": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 4),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "net_pnl_usd": round(total_pnl_usd, 2),
    }
    await _post("daily_stats", row)


def fire_and_forget(coro):
    """Schedule a coroutine without waiting for it."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass
