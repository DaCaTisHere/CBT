"""
Honeypot Detector - Lightweight scam/honeypot token detection via GoPlus API.

Checks before trading:
- is_honeypot flag
- buy/sell tax thresholds (>10% = unsafe)
- cannot_sell_all flag
- owner_change_balance flag
- proxy without open source

GoPlus API is free, no key needed.
"""

import ssl
import time
from typing import Dict, Any

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)

CHAIN_IDS = {
    "bsc": "56",
    "base": "8453",
    "ethereum": "1",
    "eth": "1",
    "arbitrum": "42161",
}

GOPLUS_BASE_URL = "https://api.gopluslabs.com/api/v1/token_security"

MAX_BUY_TAX = 0.10
MAX_SELL_TAX = 0.10
CACHE_TTL = 600

_cache: Dict[str, Dict[str, Any]] = {}
_cache_ts: Dict[str, float] = {}


async def check_token(token_address: str, chain: str) -> Dict[str, Any]:
    """
    Check a token for honeypot/scam indicators via GoPlus API.

    Args:
        token_address: EVM token contract address
        chain: Network name ("bsc", "base", "ethereum", "arbitrum")

    Returns:
        dict with keys: is_safe, risk_level, reasons, details
    """
    cache_key = f"{chain}:{token_address.lower()}"
    now = time.time()

    if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    chain_id = CHAIN_IDS.get(chain)
    if not chain_id:
        result = _fail_safe(f"Unsupported chain: {chain}")
        _set_cache(cache_key, result, now)
        return result

    try:
        url = f"{GOPLUS_BASE_URL}/{chain_id}?contract_addresses={token_address}"
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    result = _fail_safe(f"GoPlus API HTTP {resp.status}")
                    _set_cache(cache_key, result, now)
                    return result

                data = await resp.json()

        token_data = data.get("result", {}).get(token_address.lower(), {})
        if not token_data:
            result = _fail_safe("Token not found in GoPlus")
            _set_cache(cache_key, result, now)
            return result

        result = _evaluate(token_data)
        _set_cache(cache_key, result, now)

        if not result["is_safe"]:
            logger.warning(
                f"[HONEYPOT] 🍯 {token_address[:16]}... on {chain} UNSAFE "
                f"(risk={result['risk_level']}): {result['reasons']}"
            )
        else:
            logger.info(
                f"[HONEYPOT] ✅ {token_address[:16]}... on {chain} safe "
                f"(risk={result['risk_level']})"
            )

        return result

    except Exception as e:
        logger.error(f"[HONEYPOT] GoPlus error for {token_address[:16]}...: {e}")
        result = _fail_safe(str(e))
        _set_cache(cache_key, result, now)
        return result


def _evaluate(token_data: dict) -> Dict[str, Any]:
    """Evaluate GoPlus response and determine safety."""
    reasons = []
    risk_score = 0

    is_honeypot = token_data.get("is_honeypot", "0") == "1"
    if is_honeypot:
        reasons.append("is_honeypot")
        risk_score += 100

    cannot_sell = token_data.get("cannot_sell_all", "0") == "1"
    if cannot_sell:
        reasons.append("cannot_sell_all")
        risk_score += 80

    owner_change = token_data.get("owner_change_balance", "0") == "1"
    if owner_change:
        reasons.append("owner_change_balance")
        risk_score += 60

    buy_tax = _parse_tax(token_data.get("buy_tax", "0"))
    sell_tax = _parse_tax(token_data.get("sell_tax", "0"))

    if sell_tax > MAX_SELL_TAX:
        reasons.append(f"sell_tax={sell_tax * 100:.1f}%")
        risk_score += 70

    if buy_tax > MAX_BUY_TAX:
        reasons.append(f"buy_tax={buy_tax * 100:.1f}%")
        risk_score += 40

    is_proxy = token_data.get("is_proxy", "0") == "1"
    is_open_source = token_data.get("is_open_source", "0") == "1"

    if is_proxy and not is_open_source:
        reasons.append("proxy_not_open_source")
        risk_score += 20

    if risk_score >= 80:
        risk_level = "critical"
    elif risk_score >= 50:
        risk_level = "high"
    elif risk_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    is_safe = risk_score < 50

    return {
        "is_safe": is_safe,
        "risk_level": risk_level,
        "reasons": reasons,
        "details": {
            "is_honeypot": is_honeypot,
            "buy_tax": buy_tax,
            "sell_tax": sell_tax,
            "cannot_sell_all": cannot_sell,
            "owner_change_balance": owner_change,
            "is_proxy": is_proxy,
            "is_open_source": is_open_source,
            "risk_score": risk_score,
        },
    }


def _parse_tax(val) -> float:
    """Parse tax string from GoPlus ('0.05' means 5%)."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _fail_safe(reason: str) -> Dict[str, Any]:
    """Return a fail-safe (unsafe) result when verification is impossible."""
    return {
        "is_safe": False,
        "risk_level": "unknown",
        "reasons": [f"check_failed: {reason}"],
        "details": {"error": reason},
    }


def _set_cache(key: str, result: Dict[str, Any], ts: float):
    _cache[key] = result
    _cache_ts[key] = ts
