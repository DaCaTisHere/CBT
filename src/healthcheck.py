"""HTTP healthcheck server for Railway - Modern Dashboard"""
from aiohttp import web
import asyncio
import logging
import time
import os
import aiohttp
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "changeme")

_price_cache: dict = {"prices": {}, "last_update": 0}


async def _fetch_binance_prices() -> dict:
    """Fetch ETH and BNB prices from Binance with 5-min cache."""
    global _price_cache
    if time.time() - _price_cache["last_update"] < 300 and _price_cache["prices"]:
        return _price_cache["prices"]
    fallback = {"ETHUSDT": 2050.0, "BNBUSDT": 635.0}
    try:
        async with aiohttp.ClientSession() as session:
            prices = {}
            for symbol in ("ETHUSDT", "BNBUSDT"):
                async with session.get(
                    f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        prices[symbol] = float(data["price"])
                    else:
                        prices[symbol] = fallback[symbol]
            _price_cache["prices"] = prices
            _price_cache["last_update"] = time.time()
            return prices
    except Exception:
        _price_cache["prices"] = fallback
        _price_cache["last_update"] = time.time()
        return fallback


def _check_auth(request) -> bool:
    """Return True if the request carries a valid Bearer token."""
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {DASHBOARD_TOKEN}"


def _unauthorized():
    return web.json_response({"error": "Unauthorized"}, status=401)

# Ring buffer for the last 50 log entries exposed via /logs
_log_buffer: deque = deque(maxlen=300)


class _DashboardLogHandler(logging.Handler):
    """Captures log records into the ring buffer for the /logs endpoint."""
    def emit(self, record):
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "name": record.name,
                "msg": self.format(record),
            }
            _log_buffer.append(entry)
        except Exception:
            pass


def install_log_handler():
    """Attach the dashboard handler to the root logger AND structlog bridge."""
    handler = _DashboardLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    from src.utils.logger import set_dashboard_buffer
    set_dashboard_buffer(_log_buffer)


def get_trading_mode():
    """Get current trading mode, checking safety manager for auto-unlock status"""
    try:
        from src.core.safety_manager import get_safety_manager
        sm = get_safety_manager()
        if not sm.is_simulation_mode():
            return "REAL", "#00ff88"
    except Exception:
        pass

    mode = os.getenv("TRADING_MODE", "SIMULATION").upper()
    simulation = os.getenv("SIMULATION_MODE", "true").lower() == "true"

    if mode == "REAL" and not simulation:
        return "REAL", "#00ff88"
    elif mode == "DRY_RUN":
        return "DRY RUN", "#00d4ff"
    else:
        return "SIMULATION", "#ffaa00"

# Cache for wallet balances (avoid fetching every request)
_wallet_cache = {"balances": {}, "total_usd": 0, "last_update": 0}

async def get_real_wallet_balance():
    """Get real wallet balance from DEX Trader"""
    global _wallet_cache
    try:
        if time.time() - _wallet_cache["last_update"] < 60 and _wallet_cache["total_usd"] > 0:
            return _wallet_cache["balances"], _wallet_cache["total_usd"]

        try:
            from web3 import Web3
            from src.core.config import settings as _cfg

            binance = await _fetch_binance_prices()
            eth_price = binance.get("ETHUSDT", 2050.0)
            bnb_price = binance.get("BNBUSDT", 635.0)
            prices = {"base": eth_price, "bsc": bnb_price, "arbitrum": eth_price}

            rpcs = {
                "BASE": ("base", getattr(_cfg, 'BASE_RPC_URL', None), "ETH"),
                "BSC": ("bsc", getattr(_cfg, 'BSC_RPC_URL', None), "BNB"),
                "ARBITRUM": ("arbitrum", getattr(_cfg, 'ARBITRUM_RPC_URL', None), "ETH"),
            }
            balances = {}
            total_usd = 0.0
            pk = _cfg.WALLET_PRIVATE_KEY
            addr = Web3().eth.account.from_key(pk).address
            for label, (net, rpc, sym) in rpcs.items():
                if rpc:
                    w3 = Web3(Web3.HTTPProvider(rpc))
                    bal = w3.eth.get_balance(addr) / 1e18
                    usd = bal * prices.get(net, eth_price)
                    balances[label] = {"symbol": sym, "balance": round(bal, 6), "usd": round(usd, 2)}
                    total_usd += usd
        except Exception:
            balances = {}
            total_usd = 0.0

        _wallet_cache["balances"] = balances
        _wallet_cache["total_usd"] = total_usd
        _wallet_cache["last_update"] = time.time()

        return balances, total_usd
    except Exception as e:
        logger.error(f"Error getting wallet balance: {e}")
        return {}, 0

def get_trading_stats():
    """Get real trading stats from safety_manager (primary) + sniper positions"""
    try:
        from src.core.safety_manager import get_safety_manager
        sm = get_safety_manager()
        status = sm.get_status()

        sim = status.get("simulation", {})
        mom = status.get("momentum", {})
        grid = status.get("grid", {})

        total_trades = sim.get("trades", 0)
        won = sim.get("won", 0)
        lost = sim.get("lost", 0)
        wr_str = sim.get("win_rate", "0%")
        try:
            win_rate = float(wr_str.replace("%", ""))
        except Exception:
            win_rate = 0.0
        pnl_str = sim.get("total_pnl", "$+0.00")
        try:
            total_pnl = float(pnl_str.replace("$", "").replace("+", "").replace(",", ""))
        except Exception:
            total_pnl = 0.0

        avg_win_str = sim.get("avg_win", "+0%")
        avg_loss_str = sim.get("avg_loss", "0%")

        sniper_positions = {}
        try:
            from src.core.orchestrator import Orchestrator
            orch = Orchestrator._instance if hasattr(Orchestrator, '_instance') else None
            if orch:
                for attr_name in dir(orch):
                    obj = getattr(orch, attr_name, None)
                    if obj and hasattr(obj, 'sniper_positions'):
                        for addr, pos in obj.sniper_positions.items():
                            entry = pos.get("entry_price", 0)
                            symbol = pos.get("symbol", addr[:8])
                            sniper_positions[symbol] = {
                                'entry_price': entry,
                                'current_price': pos.get("highest_price", entry),
                                'amount': float(pos.get("amount_remaining", 0)),
                                'value': float(pos.get("amount_remaining", 0)) * entry,
                                'pnl_pct': 0,
                                'stop_loss': pos.get("sl_price", 0),
                                'take_profit': pos.get("tp1_price", 0),
                                'trailing_activated': True,
                                'tp1_hit': pos.get("tp1_hit", False),
                                'tp2_hit': pos.get("tp2_hit", False),
                                'entry_time': pos.get("entry_time", datetime.now(timezone.utc)).isoformat() if hasattr(pos.get("entry_time"), 'isoformat') else None,
                                'network': pos.get("network", ""),
                            }
                        break
        except Exception:
            pass

        progress = sm.get_progress_bar()
        needed = max(0, sm.MIN_SIM_TRADES - total_trades)
        safety_info = status.get("safety", {})

        return {
            'current_value': 10000 + total_pnl,
            'total_pnl': total_pnl,
            'total_pnl_percent': (total_pnl / 10000) * 100 if total_pnl else 0,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'winning_trades': won,
            'losing_trades': lost,
            'avg_win': avg_win_str,
            'avg_loss': avg_loss_str,
            'positions': sniper_positions,
            'open_positions': len(sniper_positions),
            'progress_bar': progress,
            'needed_for_unlock': needed,
            'grid_trades': grid.get("trades", 0),
            'grid_wr': grid.get("win_rate", "0%"),
            'grid_pnl': grid.get("pnl", "$0"),
            'mom_trades': mom.get("trades", 0),
            'mom_wr': mom.get("win_rate", "0%"),
            'mom_pnl': mom.get("pnl", "$0"),
            'is_unlocked': safety_info.get("real_trading_unlocked", False),
            'unlock_reason': safety_info.get("unlock_reason", ""),
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return None


def get_momentum_stats():
    """Get momentum detector stats from the orchestrator's watchlist if available"""
    try:
        from src.core.orchestrator import Orchestrator
        orch = Orchestrator._instance if hasattr(Orchestrator, '_instance') else None
        if orch and hasattr(orch, 'momentum_detector') and orch.momentum_detector:
            detector = orch.momentum_detector
            return {
                'btc_trend': getattr(detector, 'btc_trend', 'neutral'),
                'last_signals': getattr(detector, 'last_signals', [])[-10:],
            }
        return {
            'btc_trend': 'neutral',
            'last_signals': []
        }
    except Exception as e:
        logger.debug(f"Momentum stats unavailable: {e}")
        return None

def get_ml_info():
    """Get ML auto-learner info if available"""
    try:
        from src.trading.paper_trader import get_paper_trader
        trader = get_paper_trader()
        
        if trader.auto_learner:
            stats = trader.auto_learner.get_stats()
            return {
                "is_trained": stats.get("is_trained", False),
                "total_records": stats.get("total_records", 0),
                "completed_trades": stats.get("completed_trades", 0),
                "win_rate": stats.get("win_rate", "0%"),
                "avg_win": stats.get("avg_win", "+0%"),
                "avg_loss": stats.get("avg_loss", "0%"),
                "last_trained": stats.get("last_trained", "Never"),
                "best_hours": stats.get("best_hours", {}),
                "signal_success": stats.get("signal_success_rates", {})
            }
    except Exception as e:
        logger.error(f"Error getting ML info: {e}")
    return None

# Global state
_start_time = time.time()
_status = {"running": True, "modules": []}

def update_status(modules: list):
    """Update bot status for health endpoint"""
    global _status
    _status["modules"] = modules

async def health(request):
    """Health check endpoint - returns OK"""
    return web.Response(text="OK", status=200)

async def status(request):
    """Status endpoint - returns bot info as JSON"""
    if not _check_auth(request):
        return _unauthorized()
    uptime = time.time() - _start_time
    trading_stats = get_trading_stats()
    ml_info = get_ml_info()
    mode_name, _ = get_trading_mode()
    wallet_balances, wallet_total_usd = await get_real_wallet_balance()
    
    # Debug: show actual settings value vs env var
    try:
        from src.core.config import settings as _s
        _settings_sim = _s.SIMULATION_MODE
    except Exception as e:
        logger.debug(f"Could not read SIMULATION_MODE from settings: {e}")
        _settings_sim = "import_error"
    
    data = {
        "status": "running",
        "uptime_seconds": int(uptime),
        "uptime_hours": round(uptime / 3600, 2),
        "version": "11.0",
        "mode": mode_name.lower(),
        "debug": {
            "env_SIMULATION_MODE": os.getenv("SIMULATION_MODE", "NOT_SET"),
            "settings_SIMULATION_MODE": str(_settings_sim),
            "env_TRADING_MODE": os.getenv("TRADING_MODE", "NOT_SET"),
            "env_DRY_RUN": os.getenv("DRY_RUN", "NOT_SET"),
        },
        "modules": _status.get("modules", []),
        "wallet": {
            "total_usd": wallet_total_usd,
            "balances": wallet_balances
        },
        "paper_trading": trading_stats,
        "ml_model": ml_info
    }
    return web.json_response(data)

async def index(request):
    """Root endpoint - Modern Dashboard"""
    uptime = time.time() - _start_time
    stats = get_trading_stats()
    mode_name, mode_color = get_trading_mode()
    
    wallet_balances, wallet_total_usd = await get_real_wallet_balance()
    is_real_mode = mode_name == "REAL"
    
    # Format trading stats
    if is_real_mode and wallet_total_usd > 0:
        # In REAL mode, show actual wallet balance
        portfolio_value = wallet_total_usd
        total_pnl = 0  # Will track from first trade
        total_pnl_pct = 0
        total_trades = stats.get('total_trades', 0) if stats else 0
        win_rate = stats.get('win_rate', 0) if stats else 0
        winning = stats.get('winning_trades', 0) if stats else 0
        losing = stats.get('losing_trades', 0) if stats else 0
        positions = stats.get('positions', {}) if stats else {}
        open_positions = stats.get('open_positions', 0) if stats else 0
    elif stats:
        portfolio_value = stats.get('current_value', 10000)
        total_pnl = stats.get('total_pnl', 0)
        total_pnl_pct = stats.get('total_pnl_percent', 0)
        total_trades = stats.get('total_trades', 0)
        win_rate = stats.get('win_rate', 0)
        winning = stats.get('winning_trades', 0)
        losing = stats.get('losing_trades', 0)
        positions = stats.get('positions', {})
        open_positions = stats.get('open_positions', 0)
    else:
        portfolio_value = 10000
        total_pnl = 0
        total_pnl_pct = 0
        total_trades = 0
        win_rate = 0
        winning = 0
        losing = 0
        positions = {}
        open_positions = 0
    
    ml_trained = False
    ml_samples = 0
    ml_win_rate = '0%'
    ml_avg_win = '+0%'
    ml_avg_loss = '0%'
    ml_last_trained = 'Never'
    
    # Colors
    pnl_color = '#00ff88' if total_pnl >= 0 else '#ff4444'
    pnl_sign = '+' if total_pnl >= 0 else ''
    
    # Format uptime
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    uptime_str = f"{hours}h {minutes}m"
    
    # Generate positions HTML with PnL
    if positions:
        positions_items = []
        for symbol, pos in positions.items():
            entry = pos.get('entry_price', 0)
            current = pos.get('current_price', entry)
            value = pos.get('value', 0)
            pnl_pct = pos.get('pnl_pct', 0)
            sl = pos.get('stop_loss', 0)
            tp = pos.get('take_profit', 0)
            trailing = pos.get('trailing_activated', False)
            tp1 = pos.get('tp1_hit', False)
            tp2 = pos.get('tp2_hit', False)
            
            # Color based on PnL
            pnl_color = '#00ff88' if pnl_pct >= 0 else '#ff4444'
            pnl_sign = '+' if pnl_pct >= 0 else ''
            
            # Status badges
            badges = []
            if trailing:
                badges.append('<span class="badge badge-green">TRAIL</span>')
            if tp1:
                badges.append('<span class="badge badge-blue">TP1</span>')
            if tp2:
                badges.append('<span class="badge badge-purple">TP2</span>')
            badges_html = ' '.join(badges) if badges else ''
            
            # Calculate SL/TP percentages
            sl_pct = ((sl - entry) / entry * 100) if entry > 0 and sl > 0 else -4
            tp_pct = ((tp - entry) / entry * 100) if entry > 0 and tp > 0 else 10
            
            positions_items.append(f'''
                <div class="position-item">
                    <div class="position-left">
                        <span class="position-symbol">{symbol}</span>
                        <div class="position-badges">{badges_html}</div>
                    </div>
                    <div class="position-center">
                        <div class="position-prices">
                            <span class="price-label">Entry:</span> ${entry:.6f}
                            <span class="price-arrow">→</span>
                            <span class="price-label">Now:</span> ${current:.6f}
                        </div>
                        <div class="position-sltp">
                            <span class="sl">SL: {sl_pct:.1f}%</span>
                            <span class="tp">TP: +{tp_pct:.1f}%</span>
                        </div>
                    </div>
                    <div class="position-right">
                        <div class="position-pnl" style="color: {pnl_color};">{pnl_sign}{pnl_pct:.2f}%</div>
                        <div class="position-value">${value:.2f}</div>
                    </div>
                </div>''')
        positions_html = ''.join(positions_items)
    else:
        positions_html = '<div class="no-positions">No open positions</div>'
    
    # ML info
    ml_info = get_ml_info()
    ml_trained = ml_info.get("is_trained", False) if ml_info else False
    ml_records = ml_info.get("total_records", 0) if ml_info else 0

    # Momentum info
    mom_info = get_momentum_stats()
    btc_trend = mom_info.get("btc_trend", "neutral") if mom_info else "neutral"
    btc_color = "#00ff88" if btc_trend == "bullish" else "#ff4444" if btc_trend == "bearish" else "#ffaa00"

    # Grid stats
    grid_trades = stats.get('grid_trades', 0) if stats else 0
    grid_wr = stats.get('grid_wr', '0%') if stats else '0%'
    grid_pnl = stats.get('grid_pnl', '$0') if stats else '$0'
    mom_trades = stats.get('mom_trades', 0) if stats else 0
    mom_wr = stats.get('mom_wr', '0%') if stats else '0%'
    mom_pnl = stats.get('mom_pnl', '$0') if stats else '$0'

    # Wallet rows
    wallet_rows = ""
    if wallet_balances:
        for label, info in wallet_balances.items():
            wallet_rows += f'<div class="wallet-row"><span class="wallet-chain">{label}</span><span class="wallet-bal">{info["balance"]:.4f} {info["symbol"]}</span><span class="wallet-usd">${info["usd"]:.0f}</span></div>'
    else:
        wallet_rows = '<div class="wallet-row" style="color:#555;">No wallet connected</div>'

    is_unlocked = stats.get('is_unlocked', False) if stats else False
    needed = stats.get('needed_for_unlock', 20) if stats else 20
    progress_pct = min(100, (total_trades / 20) * 100) if total_trades else 0
    unlock_reason = stats.get('unlock_reason', '') if stats else ''
    locked_by_pnl = needed == 0 and not is_unlocked and total_pnl < 0

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cryptobot Dashboard</title>
<meta http-equiv="refresh" content="15">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#08090d;--card:#0f1117;--border:#1a1d28;--text:#c8ccd4;--dim:#555b6e;--accent:#3b82f6;--green:#22c55e;--red:#ef4444;--yellow:#eab308;--mono:'IBM Plex Mono',monospace;--sans:'Inter',sans-serif}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:880px;margin:0 auto;padding:24px 16px}}
header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;flex-wrap:wrap;gap:12px}}
.logo{{font-family:var(--mono);font-size:1.1rem;font-weight:700;color:#fff;letter-spacing:-.5px}}
.pills{{display:flex;gap:8px;flex-wrap:wrap}}
.pill{{font-size:.72rem;padding:5px 11px;border-radius:6px;font-weight:600;background:rgba(255,255,255,.05);border:1px solid var(--border)}}
.pill-green{{color:var(--green);border-color:rgba(34,197,94,.3)}}
.pill-yellow{{color:var(--yellow);border-color:rgba(234,179,8,.3)}}
.pill-blue{{color:var(--accent);border-color:rgba(59,130,246,.3)}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
.grid-5{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:14px}}
.card-sm{{padding:14px}}
.card-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}}
.card-label{{font-size:.7rem;text-transform:uppercase;letter-spacing:.8px;color:var(--dim);font-weight:600}}
.big-num{{font-family:var(--mono);font-size:2.4rem;font-weight:700;line-height:1}}
.big-sub{{font-family:var(--mono);font-size:1rem;margin-top:4px}}
.s-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}}
.s-item{{text-align:center;padding:10px 6px;background:rgba(255,255,255,.02);border-radius:8px}}
.s-val{{font-family:var(--mono);font-size:1.15rem;font-weight:700;color:#fff}}
.s-lbl{{font-size:.65rem;color:var(--dim);margin-top:3px;text-transform:uppercase}}
.prog-outer{{background:rgba(255,255,255,.05);border-radius:6px;height:22px;overflow:hidden;margin:10px 0}}
.prog-inner{{height:100%;border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:.7rem;font-weight:700;color:#000;background:linear-gradient(90deg,var(--accent),var(--green))}}
.strat-card{{background:rgba(255,255,255,.02);border-radius:8px;padding:14px}}
.strat-title{{font-size:.8rem;font-weight:600;color:#fff;margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.strat-row{{display:flex;justify-content:space-between;padding:4px 0;font-size:.78rem;font-family:var(--mono)}}
.strat-row span:first-child{{color:var(--dim)}}
.strat-row span:last-child{{color:#fff;font-weight:600}}
.pos-item{{display:flex;align-items:center;justify-content:space-between;padding:12px;background:rgba(59,130,246,.04);border:1px solid rgba(59,130,246,.15);border-radius:8px;margin-bottom:8px}}
.pos-sym{{font-family:var(--mono);font-weight:700;color:var(--accent);font-size:.9rem}}
.pos-meta{{font-size:.7rem;color:var(--dim);font-family:var(--mono)}}
.pos-pnl{{font-family:var(--mono);font-size:1.1rem;font-weight:700;text-align:right}}
.pos-val{{font-size:.7rem;color:var(--dim);font-family:var(--mono);text-align:right}}
.no-pos{{text-align:center;color:var(--dim);padding:16px;font-size:.85rem}}
.mod-item{{display:flex;align-items:center;gap:8px;padding:8px 12px;background:rgba(255,255,255,.02);border-radius:6px;font-size:.8rem}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}}
.dot-warn{{background:var(--yellow)}}
.wallet-row{{display:flex;justify-content:space-between;padding:5px 0;font-size:.78rem;font-family:var(--mono)}}
.wallet-chain{{color:var(--dim);min-width:70px}}
.wallet-bal{{color:var(--text)}}
.wallet-usd{{color:#fff;font-weight:600;min-width:50px;text-align:right}}
footer{{text-align:center;padding:20px;color:var(--dim);font-size:.7rem}}
@media(max-width:640px){{.s-grid,.grid-2,.grid-3{{grid-template-columns:1fr 1fr}}.grid-5{{grid-template-columns:repeat(3,1fr)}}.big-num{{font-size:1.8rem}}header{{flex-direction:column;align-items:flex-start}}}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="logo">CRYPTOBOT</div>
  <div class="pills">
    <span class="pill pill-green">RUNNING {uptime_str}</span>
    <span class="pill" style="color:{mode_color};border-color:{mode_color}33;">{mode_name}</span>
    <span class="pill" style="color:{btc_color};border-color:{btc_color}33;">BTC {btc_trend.upper()}</span>
  </div>
</header>

<div class="card">
  <div class="card-head">
    <span class="card-label">Portfolio</span>
    <span class="pill" style="color:{pnl_color};border-color:{pnl_color}33;font-family:var(--mono)">{pnl_sign}{total_pnl_pct:.2f}%</span>
  </div>
  <div class="big-num" style="color:{pnl_color}">${portfolio_value:,.2f}</div>
  <div class="big-sub" style="color:{pnl_color}">{pnl_sign}${total_pnl:,.2f}</div>
  <div class="s-grid">
    <div class="s-item"><div class="s-val">{total_trades}</div><div class="s-lbl">Trades</div></div>
    <div class="s-item"><div class="s-val" style="color:var(--green)">{winning}</div><div class="s-lbl">Wins</div></div>
    <div class="s-item"><div class="s-val" style="color:var(--red)">{losing}</div><div class="s-lbl">Losses</div></div>
    <div class="s-item"><div class="s-val">{win_rate:.1f}%</div><div class="s-lbl">Win Rate</div></div>
  </div>
</div>

<div class="grid-2">
  <div class="card card-sm">
    <div class="card-head"><span class="card-label">Grid Trading (80%)</span><span class="pill pill-blue">ETH + BNB</span></div>
    <div class="strat-row"><span>Trades</span><span>{grid_trades}</span></div>
    <div class="strat-row"><span>Win Rate</span><span>{grid_wr}</span></div>
    <div class="strat-row"><span>PnL</span><span>{grid_pnl}</span></div>
  </div>
  <div class="card card-sm">
    <div class="card-head"><span class="card-label">Momentum (20%)</span><span class="pill pill-blue">50 PAIRS</span></div>
    <div class="strat-row"><span>Trades</span><span>{mom_trades}</span></div>
    <div class="strat-row"><span>Win Rate</span><span>{mom_wr}</span></div>
    <div class="strat-row"><span>PnL</span><span>{mom_pnl}</span></div>
  </div>
</div>

<div class="card card-sm">
  <div class="card-head">
    <span class="card-label">{"Mode reel actif" if is_unlocked else "Progression vers mode reel"}</span>
    <span class="pill {"pill-green" if is_unlocked else "pill-yellow"}">{"UNLOCKED" if is_unlocked else ("PnL negatif" if locked_by_pnl else f"{needed} restants")}</span>
  </div>
  {"" if is_unlocked else f'<div class="prog-outer"><div class="prog-inner" style="width:{progress_pct:.0f}%">{total_trades}/20</div></div>'}
  <div class="grid-5" style="margin-top:10px">
    <div class="s-item"><div class="s-val" style="font-size:.95rem">{stats.get('avg_win', '+0%') if stats else '+0%'}</div><div class="s-lbl">Avg Win</div></div>
    <div class="s-item"><div class="s-val" style="font-size:.95rem">{stats.get('avg_loss', '0%') if stats else '0%'}</div><div class="s-lbl">Avg Loss</div></div>
    <div class="s-item"><div class="s-val" style="font-size:.95rem">{grid_wr}</div><div class="s-lbl">Grid WR</div></div>
    <div class="s-item"><div class="s-val" style="font-size:.95rem">{'Yes' if ml_trained else 'No'}</div><div class="s-lbl">ML</div></div>
    <div class="s-item"><div class="s-val" style="font-size:.95rem">{ml_records}</div><div class="s-lbl">Samples</div></div>
  </div>
</div>

<div class="card card-sm">
  <div class="card-head">
    <span class="card-label">Positions ({open_positions})</span>
    <span class="pill pill-blue">LIVE</span>
  </div>
  {positions_html if positions_html != '<div class="no-positions">No open positions</div>' else '<div class="no-pos">Aucune position ouverte</div>'}
</div>

<div class="grid-2">
  <div class="card card-sm">
    <div class="card-head"><span class="card-label">Sniper Config</span></div>
    <div class="strat-row"><span>Chains</span><span>BSC + Base</span></div>
    <div class="strat-row"><span>Liq. min</span><span>$10k</span></div>
    <div class="strat-row"><span>Confirm</span><span>+8% x3</span></div>
    <div class="strat-row"><span>TP</span><span>30 / 75 / 150%</span></div>
    <div class="strat-row"><span>SL</span><span>-20% trailing</span></div>
    <div class="strat-row"><span>Max hold</span><span>30 min</span></div>
  </div>
  <div class="card card-sm">
    <div class="card-head"><span class="card-label">Wallet</span><span class="pill pill-green">${wallet_total_usd:.2f}</span></div>
    {wallet_rows}
    <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
      <div class="strat-row"><span>Mode</span><span>{mode_name}</span></div>
    </div>
  </div>
</div>

<div class="card card-sm">
  <div class="card-head"><span class="card-label">Modules actifs</span></div>
  <div class="grid-3">
    <div class="mod-item"><div class="dot"></div>Grid Trader</div>
    <div class="mod-item"><div class="dot"></div>Pool Detector</div>
    <div class="mod-item"><div class="dot"></div>Momentum</div>
    <div class="mod-item"><div class="dot"></div>AI Engine + OpenAI</div>
    <div class="mod-item"><div class="dot"></div>Safety Manager</div>
    <div class="mod-item"><div class="dot"></div>Telegram</div>
    <div class="mod-item"><div class="dot"></div>Honeypot (GoPlus)</div>
    <div class="mod-item"><div class="dot"></div>Rugpull Detector</div>
    <div class="mod-item"><div class="dot {"dot-warn" if not ml_trained else ""}"></div>ML AutoLearner</div>
    <div class="mod-item"><div class="dot"></div>Binance WS</div>
    <div class="mod-item"><div class="dot"></div>Supabase DB</div>
    <div class="mod-item"><div class="dot"></div>DEX Trader</div>
  </div>
</div>

<footer>Auto-refresh 15s &middot; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</footer>

</div>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def preflight(request):
    """Preflight checks for real trading"""
    try:
        from src.core.trading_mode import get_trading_mode_manager
        
        manager = get_trading_mode_manager()
        all_passed, results = await manager.run_preflight_checks()
        
        checks = []
        for check_name, (passed, message) in results.items():
            checks.append({
                "name": check_name,
                "passed": passed,
                "message": message
            })
        
        return web.json_response({
            "all_passed": all_passed,
            "current_mode": manager.get_current_mode(),
            "checks": checks,
            "instructions": manager.get_mode_switch_instructions() if not all_passed else None
        })
    except Exception as e:
        return web.json_response({
            "error": str(e),
            "all_passed": False
        }, status=500)


async def safety_status(request):
    """Safety Manager status - shows simulation progress and unlock criteria"""
    try:
        from src.core.safety_manager import get_safety_manager
        sm = get_safety_manager()
        data = sm.get_status()
        data["progress_bar"] = sm.get_progress_bar()
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def safety_reset(request):
    """Reset simulation stats for new strategy test (POST only)"""
    if not _check_auth(request):
        return _unauthorized()
    try:
        from src.core.safety_manager import get_safety_manager
        sm = get_safety_manager()
        sm.reset_simulation()
        return web.json_response({"status": "ok", "message": "Simulation stats reset"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def evolve_status(request):
    """Auto-evolution status and trigger (POST only)"""
    if not _check_auth(request):
        return _unauthorized()
    try:
        from src.core.safety_manager import get_safety_manager
        sm = get_safety_manager()
        result = sm.auto_evolve()
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def dex_status(request):
    """DEX Trader status"""
    if not _check_auth(request):
        return _unauthorized()
    try:
        from src.trading.dex_trader import DEXTrader
        from src.core.orchestrator import Orchestrator

        trader = None
        orch = Orchestrator._instance
        if orch:
            for attr in ("dex_trader",):
                if hasattr(orch, attr):
                    trader = getattr(orch, attr)
        if trader is None:
            return web.json_response({"status": "no_dex_trader", "message": "DEX Trader not initialized"})

        stats = trader.get_stats()
        if stats:
            return web.json_response({
                "status": "ready",
                "networks": stats.get("networks_connected", []),
                "total_trades": stats.get("total_trades", 0),
                "positions": stats.get("positions", {})
            })
        else:
            return web.json_response({
                "status": "not_configured",
                "message": "Wallet not configured for DEX trading",
                "instructions": [
                    "1. Add WALLET_PRIVATE_KEY to environment",
                    "2. Add ETHEREUM_RPC_URL (get free at alchemy.com)",
                    "3. Optional: Add BASE_RPC_URL, ARBITRUM_RPC_URL for more chains",
                    "4. Set SIMULATION_MODE=false to enable real trading"
                ]
            })
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)


async def grid_status(request):
    """Grid Trading Engine status"""
    try:
        from src.core.orchestrator import Orchestrator
        orch = Orchestrator._instance if hasattr(Orchestrator, '_instance') else None
        if orch and hasattr(orch, 'grid_trader') and orch.grid_trader:
            return web.json_response(orch.grid_trader.get_status())
        return web.json_response({"status": "not_running", "message": "Grid trader not initialized"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def grid_backtest(request):
    """Run grid backtest on loaded history"""
    try:
        from src.core.orchestrator import Orchestrator
        orch = Orchestrator._instance if hasattr(Orchestrator, '_instance') else None
        if orch and hasattr(orch, 'grid_trader') and orch.grid_trader:
            results = {}
            for pair_id in orch.grid_trader.GRID_PAIRS:
                results[pair_id] = orch.grid_trader.backtest(pair_id)
            return web.json_response(results)
        return web.json_response({"status": "not_running"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def logs_endpoint(request):
    """Return the last 50 log entries as JSON."""
    if not _check_auth(request):
        return _unauthorized()
    return web.json_response(list(_log_buffer))


async def positions_endpoint(request):
    """Return current sniper (DEX) positions with live PnL."""
    if not _check_auth(request):
        return _unauthorized()
    result = {"sniper_positions": [], "paper_positions": []}
    try:
        from src.trading.dex_trader import DEXTrader
        from src.core.orchestrator import Orchestrator
        orch = Orchestrator._instance if hasattr(Orchestrator, '_instance') else None

        # Sniper / DEX positions
        if orch and hasattr(orch, 'momentum_detector'):
            try:
                dex = None
                for attr in ("dex_trader",):
                    if hasattr(orch, attr):
                        dex = getattr(orch, attr)
                if dex is None:
                    dex = None
                for addr, pos in getattr(dex, "sniper_positions", {}).items():
                    entry = pos.get("buy_price", pos.get("price_usd", 0))
                    current = pos.get("current_price", entry)
                    pnl_pct = ((current - entry) / entry * 100) if entry > 0 else 0
                    result["sniper_positions"].append({
                        "token": pos.get("token_symbol", "?"),
                        "network": pos.get("network", "?"),
                        "entry_price": entry,
                        "current_price": current,
                        "amount_usd": pos.get("amount_usd", 0),
                        "pnl_pct": round(pnl_pct, 2),
                        "age_minutes": round(
                            (time.time() - pos.get("buy_time", time.time())) / 60, 1
                        ),
                    })
            except Exception as e:
                result["sniper_error"] = str(e)

        # Paper trading positions
        try:
            from src.trading.paper_trader import get_paper_trader
            pt = get_paper_trader()
            for symbol, p in pt.portfolio.positions.items():
                current = pt.price_cache.get(symbol, p.entry_price)
                pnl_pct = ((current - p.entry_price) / p.entry_price * 100) if p.entry_price > 0 else 0
                result["paper_positions"].append({
                    "symbol": symbol,
                    "entry_price": p.entry_price,
                    "current_price": current,
                    "value": p.value,
                    "pnl_pct": round(pnl_pct, 2),
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                })
        except Exception as e:
            result["paper_error"] = str(e)

    except Exception as e:
        result["error"] = str(e)

    return web.json_response(result)


async def start_healthcheck_server(port=8080):
    """Start healthcheck server on specified port"""
    install_log_handler()

    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_get('/status', status)
    app.router.add_get('/preflight', preflight)
    app.router.add_get('/dex', dex_status)
    app.router.add_get('/safety', safety_status)
    app.router.add_post('/safety/reset', safety_reset)
    app.router.add_post('/evolve', evolve_status)
    app.router.add_get('/grid', grid_status)
    app.router.add_get('/backtest', grid_backtest)
    app.router.add_get('/logs', logs_endpoint)
    app.router.add_get('/positions', positions_endpoint)
    app.router.add_get('/', index)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Healthcheck server running on port {port}")
    
    return runner

if __name__ == "__main__":
    asyncio.run(start_healthcheck_server())
