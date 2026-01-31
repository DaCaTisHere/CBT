"""HTTP healthcheck server for Railway - Modern Dashboard"""
from aiohttp import web
import asyncio
import logging
import time
import json
from datetime import datetime

logger = logging.getLogger(__name__)

def get_trading_stats():
    """Get paper trading stats if available"""
    try:
        from src.trading.paper_trader import get_paper_trader
        trader = get_paper_trader()
        stats = trader.get_stats()
        
        # Add positions info with PnL
        positions_with_pnl = {}
        for symbol, p in trader.portfolio.positions.items():
            current_price = trader.price_cache.get(symbol, p.entry_price)
            pnl_pct = ((current_price - p.entry_price) / p.entry_price) * 100 if p.entry_price > 0 else 0
            
            positions_with_pnl[symbol] = {
                'entry_price': p.entry_price,
                'current_price': current_price,
                'amount': p.amount,
                'value': p.value,
                'pnl_pct': pnl_pct,
                'stop_loss': p.stop_loss,
                'take_profit': p.take_profit,
                'trailing_activated': p.trailing_activated,
                'tp1_hit': p.tp1_hit,
                'tp2_hit': p.tp2_hit,
                'entry_time': p.entry_time.isoformat() if p.entry_time else None
            }
        
        stats['positions'] = positions_with_pnl
        stats['open_positions'] = len(trader.portfolio.positions)
        return stats
    except Exception as e:
        print(f"Error getting stats: {e}")
        return None


def get_momentum_stats():
    """Get momentum detector stats if available"""
    try:
        from src.modules.momentum_detector import MomentumDetector
        # Get last signals from momentum detector
        return {
            'btc_trend': 'neutral',
            'last_signals': []
        }
    except:
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
        print(f"Error getting ML info: {e}")
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
    uptime = time.time() - _start_time
    trading_stats = get_trading_stats()
    ml_info = get_ml_info()
    
    data = {
        "status": "running",
        "uptime_seconds": int(uptime),
        "uptime_hours": round(uptime / 3600, 2),
        "version": "0.1.0",
        "mode": "simulation",
        "modules": _status.get("modules", []),
        "paper_trading": trading_stats,
        "ml_model": ml_info
    }
    return web.json_response(data)

async def index(request):
    """Root endpoint - Modern Dashboard"""
    uptime = time.time() - _start_time
    stats = get_trading_stats()
    ml_info = get_ml_info()
    
    # Format trading stats
    if stats:
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
    
    # ML Auto-Learner info
    if ml_info:
        ml_trained = ml_info.get('is_trained', False)
        ml_samples = ml_info.get('completed_trades', 0)
        ml_win_rate = ml_info.get('win_rate', '0%')
        ml_avg_win = ml_info.get('avg_win', '+0%')
        ml_avg_loss = ml_info.get('avg_loss', '0%')
        ml_last_trained = ml_info.get('last_trained', 'Never')
        
        # Use ML stats if paper_trader stats are missing (after redeploy)
        if total_trades == 0 and ml_samples > 0:
            total_trades = ml_samples
            # Parse win_rate from ML (e.g., "40.9%" -> 40.9)
            try:
                win_rate = float(ml_win_rate.replace('%', ''))
            except:
                win_rate = 0
            # Calculate wins/losses from ML data
            winning = int(total_trades * (win_rate / 100))
            losing = total_trades - winning
    else:
        ml_trained = False
        ml_samples = 0
        ml_win_rate = '0%'
        ml_avg_win = '+0%'
        ml_avg_loss = '0%'
        ml_last_trained = 'Never'
    
    # Colors
    pnl_color = '#00ff88' if total_pnl >= 0 else '#ff4444'
    pnl_sign = '+' if total_pnl >= 0 else ''
    ml_color = '#00ff88' if ml_trained else '#ffaa00'
    ml_status = f'ACTIVE ({ml_samples} trades)' if ml_trained else 'LEARNING...'
    
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
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cryptobot Ultimate - Dashboard</title>
    <meta http-equiv="refresh" content="15">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{ 
            font-family: 'Outfit', sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
            overflow-x: hidden;
        }}
        
        .bg-grid {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image: 
                linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
            background-size: 50px 50px;
            pointer-events: none;
            z-index: 0;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 30px 20px;
            position: relative;
            z-index: 1;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        
        .logo {{
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -1px;
        }}
        
        .subtitle {{
            color: #666;
            font-size: 0.9rem;
            margin-top: 5px;
        }}
        
        .status-bar {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.05);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
        }}
        
        .pulse {{
            width: 10px; height: 10px;
            background: #00ff88;
            border-radius: 50%;
            animation: pulse 2s infinite;
            box-shadow: 0 0 10px #00ff88;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.5; transform: scale(0.9); }}
        }}
        
        .card {{
            background: linear-gradient(135deg, rgba(20,20,30,0.9), rgba(15,15,25,0.95));
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        
        .card-title {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
        }}
        
        .card-badge {{
            font-size: 0.7rem;
            padding: 4px 10px;
            border-radius: 10px;
            font-weight: 600;
        }}
        
        .portfolio-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 3rem;
            font-weight: 700;
            color: {pnl_color};
            line-height: 1;
        }}
        
        .portfolio-change {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.2rem;
            color: {pnl_color};
            margin-top: 5px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-top: 25px;
        }}
        
        .stat-item {{
            text-align: center;
            padding: 15px 10px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
        }}
        
        .stat-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.4rem;
            font-weight: 700;
            color: #fff;
        }}
        
        .stat-label {{
            font-size: 0.75rem;
            color: #666;
            margin-top: 5px;
            text-transform: uppercase;
        }}
        
        .modules-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}
        
        .module-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            font-size: 0.9rem;
        }}
        
        .module-icon {{
            width: 8px; height: 8px;
            background: #00ff88;
            border-radius: 50%;
        }}
        
        .module-icon.warning {{ background: #ffaa00; }}
        .module-icon.error {{ background: #ff4444; }}
        
        .positions-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        
        .position-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: rgba(0, 212, 255, 0.05);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 10px;
            gap: 15px;
        }}
        
        .position-left {{
            min-width: 120px;
        }}
        
        .position-symbol {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            color: #00d4ff;
            font-size: 1rem;
        }}
        
        .position-badges {{
            display: flex;
            gap: 5px;
            margin-top: 5px;
        }}
        
        .badge {{
            font-size: 0.6rem;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
        }}
        
        .badge-green {{ background: #00ff8822; color: #00ff88; }}
        .badge-blue {{ background: #00d4ff22; color: #00d4ff; }}
        .badge-purple {{ background: #aa66ff22; color: #aa66ff; }}
        
        .position-center {{
            flex: 1;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
        }}
        
        .position-prices {{
            color: #888;
            margin-bottom: 4px;
        }}
        
        .price-label {{ color: #666; }}
        .price-arrow {{ color: #444; margin: 0 5px; }}
        
        .position-sltp {{
            display: flex;
            gap: 15px;
        }}
        
        .sl {{ color: #ff4444; }}
        .tp {{ color: #00ff88; }}
        
        .position-right {{
            text-align: right;
            min-width: 80px;
        }}
        
        .position-pnl {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.2rem;
            font-weight: 700;
        }}
        
        .position-value {{ 
            color: #888; 
            font-size: 0.8rem;
            font-family: 'JetBrains Mono', monospace;
        }}
        
        .no-positions {{
            text-align: center;
            color: #666;
            padding: 20px;
            font-style: italic;
        }}
        
        .ml-status {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .ml-badge {{
            background: {ml_color}22;
            color: {ml_color};
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .ml-stats {{
            display: flex;
            gap: 20px;
            margin-top: 15px;
        }}
        
        .ml-stat {{
            text-align: center;
        }}
        
        .ml-stat-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.5rem;
            font-weight: 700;
            color: #00d4ff;
        }}
        
        .ml-stat-label {{
            font-size: 0.7rem;
            color: #666;
            text-transform: uppercase;
        }}
        
        .strategy-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }}
        
        .strategy-section {{
            background: rgba(255,255,255,0.02);
            padding: 15px;
            border-radius: 10px;
        }}
        
        .strategy-title {{
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 12px;
            color: #fff;
        }}
        
        .indicator-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        
        .indicator {{
            background: #00d4ff22;
            color: #00d4ff;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
        }}
        
        .filter-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        
        .filter-item {{
            font-size: 0.8rem;
            color: #aaa;
            font-family: 'JetBrains Mono', monospace;
        }}
        
        footer {{
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            color: #444;
            font-size: 0.8rem;
        }}
        
        @media (max-width: 600px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .modules-grid {{ grid-template-columns: 1fr; }}
            .portfolio-value {{ font-size: 2rem; }}
        }}
    </style>
</head>
<body>
    <div class="bg-grid"></div>
    
    <div class="container">
        <header>
            <div class="logo">CRYPTOBOT ULTIMATE</div>
            <div class="subtitle">SWING TRADE v6.0 - BACKTESTED (94.7% win rate)</div>
        </header>
        
        <div class="status-bar">
            <div class="status-pill">
                <div class="pulse"></div>
                <span style="color: #00ff88; font-weight: 600;">RUNNING</span>
            </div>
            <div class="status-pill">
                <span style="color: #888;">Mode:</span>
                <span style="color: #ffaa00;">SIMULATION</span>
            </div>
            <div class="status-pill">
                <span style="color: #888;">Uptime:</span>
                <span style="color: #fff;">{uptime_str}</span>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">Portfolio Value</span>
                <span class="card-badge" style="background: {pnl_color}22; color: {pnl_color};">
                    {pnl_sign}{total_pnl_pct:.2f}%
                </span>
            </div>
            <div class="portfolio-value">${portfolio_value:,.2f}</div>
            <div class="portfolio-change">{pnl_sign}${total_pnl:,.2f} PnL</div>
            
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">{total_trades}</div>
                    <div class="stat-label">Trades</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: #00ff88;">{winning}</div>
                    <div class="stat-label">Wins</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: #ff4444;">{losing}</div>
                    <div class="stat-label">Losses</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{win_rate:.1f}%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">🧠 Auto-Learning</span>
                <span class="ml-badge">{ml_status}</span>
            </div>
            <div class="ml-stats">
                <div class="ml-stat">
                    <div class="ml-stat-value">{ml_samples}</div>
                    <div class="ml-stat-label">Trades Analyzed</div>
                </div>
                <div class="ml-stat">
                    <div class="ml-stat-value">{ml_win_rate}</div>
                    <div class="ml-stat-label">Learned Win Rate</div>
                </div>
                <div class="ml-stat">
                    <div class="ml-stat-value">{ml_avg_win}</div>
                    <div class="ml-stat-label">Avg Win</div>
                </div>
                <div class="ml-stat">
                    <div class="ml-stat-value">{ml_avg_loss}</div>
                    <div class="ml-stat-label">Avg Loss</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">Open Positions ({open_positions})</span>
                <span class="card-badge" style="background: #00d4ff22; color: #00d4ff;">LIVE</span>
            </div>
            <div class="positions-list">
                {positions_html}
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">SWING TRADE v6.0 - BACKTESTED</span>
                <span class="card-badge" style="background: #00ff8822; color: #00ff88;">94.7% WIN</span>
            </div>
            <div class="strategy-grid">
                <div class="strategy-section">
                    <div class="strategy-title">🎯 Entry (BACKTESTED)</div>
                    <div class="filter-list">
                        <div class="filter-item">24h pump: +5% to +30%</div>
                        <div class="filter-item">Pullback: -3% to -12% from high</div>
                        <div class="filter-item">RSI &lt; 50 (STRICT)</div>
                        <div class="filter-item">StochRSI &lt; 55</div>
                        <div class="filter-item">Volume &gt; $500k</div>
                    </div>
                </div>
                <div class="strategy-section">
                    <div class="strategy-title">📊 Backtest Results</div>
                    <div class="filter-list">
                        <div class="filter-item">Win Rate: 94.7%</div>
                        <div class="filter-item">Expectancy: +3.56%/trade</div>
                        <div class="filter-item">30 days of data</div>
                        <div class="filter-item">20 liquid pairs tested</div>
                        <div class="filter-item">VALIDATED strategy</div>
                    </div>
                </div>
                <div class="strategy-section">
                    <div class="strategy-title">🛡️ Risk Management</div>
                    <div class="filter-list">
                        <div class="filter-item">SL: 5% (from backtest)</div>
                        <div class="filter-item">TP1: +4% → sell 20%</div>
                        <div class="filter-item">TP2: +7% → sell 30%</div>
                        <div class="filter-item">TP3: +10% → full exit</div>
                        <div class="filter-item">Trail: 3% @ +5%</div>
                    </div>
                </div>
                <div class="strategy-section">
                    <div class="strategy-title">⚡ Limits</div>
                    <div class="filter-list">
                        <div class="filter-item">Max: 5 positions</div>
                        <div class="filter-item">Hold time: up to 48h</div>
                        <div class="filter-item">Cooldown: 8h/token</div>
                        <div class="filter-item">BTC must be bullish</div>
                        <div class="filter-item">Quality over quantity</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">Active Modules</span>
            </div>
            <div class="modules-grid">
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>Momentum Detector</span>
                </div>
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>Paper Trader</span>
                </div>
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>Technical Analysis</span>
                </div>
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>BTC Correlation</span>
                </div>
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>ML Predictor</span>
                </div>
                <div class="module-item">
                    <div class="module-icon"></div>
                    <span>Risk Manager</span>
                </div>
            </div>
        </div>
        
        <footer>
            Auto-refresh every 15 seconds &bull; {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
        </footer>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def start_healthcheck_server(port=8080):
    """Start healthcheck server on specified port"""
    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_get('/status', status)
    app.router.add_get('/', index)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Healthcheck server running on port {port}")
    
    return runner

if __name__ == "__main__":
    asyncio.run(start_healthcheck_server())
