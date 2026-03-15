"""
Core Orchestrator - Central coordination of all trading modules

Responsibilities:
- Initialize and manage all strategy modules
- Allocate capital across strategies
- Coordinate inter-module communication
- Monitor system health
- Handle graceful shutdown
"""

import asyncio
import signal
import aiohttp
from typing import Dict, Optional, Any
from datetime import datetime
import logging

from src.core.config import settings
from src.core.risk_manager import RiskManager
from src.utils.logger import get_logger
from src.data.storage.database import Database

# Strategy modules (SniperBot requires web3, may be a dummy if not installed)
from src.modules.sniper import SniperBot
from src.modules.news_trader.news_trader import NewsTrader
from src.modules.sentiment.sentiment_analyzer import SentimentAnalyzer
from src.modules.ml_predictor.ml_predictor import MLPredictor
from src.modules.arbitrage.arbitrage_engine import ArbitrageEngine
from src.modules.defi_optimizer.defi_optimizer import DeFiOptimizer
from src.modules.copy_trading.copy_trader import CopyTrader
from src.execution.order_engine import OrderEngine
from src.execution.wallet_manager import WalletManager


logger = get_logger(__name__)


class Orchestrator:
    """
    Central orchestrator managing all trading strategies and system components
    """
    
    _instance = None  # Singleton for healthcheck access

    def __init__(self):
        """Initialize orchestrator"""
        self.logger = logger
        self.risk_manager = RiskManager()
        self.database: Optional[Database] = None
        
        # Execution components
        self.order_engine: Optional[OrderEngine] = None
        self.wallet_manager: Optional[WalletManager] = None
        
        # Strategy modules dictionary
        self.modules: Dict[str, Any] = {}
        
        # System state
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.total_trades = 0
        self.total_pnl = 0.0
        self.grid_trader = None
        
        Orchestrator._instance = self
        
        # Capital allocation (percentage per strategy)
        self.capital_allocation = {
            "sniper": 20.0,
            "news_trader": 25.0,
            "sentiment": 15.0,
            "ml_predictor": 15.0,
            "arbitrage": 15.0,
            "defi_optimizer": 5.0,
            "copy_trading": 5.0,
        }
        
        self.logger.info(f"[ORCHESTRATOR] Initialized - {settings.PROJECT_NAME} v{settings.VERSION}")
        self.logger.info(f"[INFO] Environment: {settings.ENVIRONMENT.value}")
        self.logger.info(f"[TEST] Testnet mode: {settings.USE_TESTNET}")
    
    async def initialize(self):
        """Initialize all system components"""
        self.logger.info("[INIT] Initializing system components...")
        
        try:
            # Initialize database (optional in simulation mode)
            if not settings.SIMULATION_MODE or settings.DATABASE_URL:
                self.database = Database()
                await self.database.connect()
                self.logger.info("[OK] Database connected")
            else:
                self.logger.warning("[WARN] Database skipped (simulation mode)")
            
            # Initialize risk manager
            await self.risk_manager.initialize()
            self.logger.info("[OK] Risk manager initialized")
            
            # Initialize execution components
            self.wallet_manager = WalletManager()
            await self.wallet_manager.initialize()
            self.logger.info("[OK] Wallet manager initialized")
            
            self.order_engine = OrderEngine(self.risk_manager, self.wallet_manager)
            await self.order_engine.initialize()
            self.logger.info("[OK] Order engine initialized")
            
            # Initialize strategy modules based on feature flags
            await self._initialize_modules()
            
            self.logger.info("[OK] All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Initialization failed: {e}")
            raise
    
    async def _initialize_modules(self):
        """Initialize enabled strategy modules"""
        self.logger.info("[MODULES] Initializing strategy modules...")
        
        # Module 1: Sniper Bot
        if settings.ENABLE_SNIPER:
            try:
                self.logger.info("   Sniper Bot: ENABLED")
                self.modules["sniper"] = SniperBot(
                    risk_manager=self.risk_manager,
                    order_engine=self.order_engine,
                    wallet_manager=self.wallet_manager
                )
                await self.modules["sniper"].initialize()
                self.logger.info("   ✅ Sniper Bot initialized")
            except Exception as e:
                self.logger.error(f"   ❌ Sniper Bot initialization failed: {e}")
                self.modules["sniper"] = None
        
        # Module 2: News Trader
        if settings.ENABLE_NEWS_TRADER:
            try:
                self.logger.info("   News Trader: ENABLED")
                self.modules["news_trader"] = NewsTrader(
                    risk_manager=self.risk_manager,
                    order_engine=self.order_engine
                )
                await self.modules["news_trader"].initialize()
                self.logger.info("   ✅ News Trader initialized")
            except Exception as e:
                self.logger.error(f"   ❌ News Trader initialization failed: {e}")
                self.modules["news_trader"] = None
        
        # Module 3: Sentiment Analyzer
        if settings.ENABLE_SENTIMENT:
            try:
                self.logger.info("   Sentiment Analyzer: ENABLED")
                self.modules["sentiment"] = SentimentAnalyzer(
                    risk_manager=self.risk_manager
                )
                await self.modules["sentiment"].initialize()
                self.logger.info("   ✅ Sentiment Analyzer initialized")
            except Exception as e:
                self.logger.error(f"   ❌ Sentiment Analyzer initialization failed: {e}")
                self.modules["sentiment"] = None
        
        # Module 4: ML Predictor
        if settings.ENABLE_ML_PREDICTOR:
            try:
                self.logger.info("   ML Predictor: ENABLED")
                self.modules["ml_predictor"] = MLPredictor(
                    risk_manager=self.risk_manager
                )
                await self.modules["ml_predictor"].initialize()
                self.logger.info("   ✅ ML Predictor initialized")
            except Exception as e:
                self.logger.error(f"   ❌ ML Predictor initialization failed: {e}")
                self.modules["ml_predictor"] = None
        
        # Module 5: Arbitrage Engine
        if settings.ENABLE_ARBITRAGE:
            try:
                self.logger.info("   Arbitrage Engine: ENABLED")
                self.modules["arbitrage"] = ArbitrageEngine(
                    risk_manager=self.risk_manager,
                    order_engine=self.order_engine
                )
                await self.modules["arbitrage"].initialize()
                self.logger.info("   ✅ Arbitrage Engine initialized")
            except Exception as e:
                self.logger.error(f"   ❌ Arbitrage Engine initialization failed: {e}")
                self.modules["arbitrage"] = None
        
        # Module 6: DeFi Optimizer
        if settings.ENABLE_DEFI_OPTIMIZER:
            try:
                self.logger.info("   DeFi Optimizer: ENABLED")
                self.modules["defi_optimizer"] = DeFiOptimizer(
                    risk_manager=self.risk_manager
                )
                await self.modules["defi_optimizer"].initialize()
                self.logger.info("   ✅ DeFi Optimizer initialized")
            except Exception as e:
                self.logger.error(f"   ❌ DeFi Optimizer initialization failed: {e}")
                self.modules["defi_optimizer"] = None
        
        # Module 7: Copy Trading
        if settings.ENABLE_COPY_TRADING:
            try:
                self.logger.info("   Copy Trading: ENABLED")
                self.modules["copy_trading"] = CopyTrader(
                    risk_manager=self.risk_manager,
                    order_engine=self.order_engine
                )
                await self.modules["copy_trading"].initialize()
                self.logger.info("   ✅ Copy Trading initialized")
            except Exception as e:
                self.logger.error(f"   ❌ Copy Trading initialization failed: {e}")
                self.modules["copy_trading"] = None
        
        enabled_count = len([m for m in self.modules.values() if m is not None])
        self.logger.info(f"[OK] {enabled_count} modules initialized")
    
    async def start(self):
        """Start the orchestrator and all modules"""
        self.logger.info("[START] Starting Cryptobot Ultimate...")
        
        try:
            # Initialize if not already done
            if self.database is None:
                await self.initialize()
            
            self.is_running = True
            self.start_time = datetime.utcnow()
            
            # Start healthcheck server for Railway
            import os
            port = int(os.getenv("PORT", 8080))
            from src.healthcheck import start_healthcheck_server
            await start_healthcheck_server(port)
            self.logger.info(f"[HTTP] Healthcheck server running on port {port}")
            
            # Initialize State Manager (persistent state)
            try:
                from src.data.state_manager import init_state_manager
                self.state_manager = await init_state_manager()
                self.logger.info("[STATE] State Manager initialized - state will persist across restarts")
            except Exception as e:
                self.logger.warning(f"[STATE] Could not init state manager: {e}")
            
            # Initialize Telegram notifications
            try:
                from src.notifications.telegram_bot import init_telegram, get_telegram_bot
                self.telegram = await init_telegram()
                if self.telegram.is_enabled:
                    await self.telegram.notify_bot_started()
                    self.logger.info("[TELEGRAM] Notifications enabled")
            except Exception as e:
                self.telegram = None
                self.logger.warning(f"[TELEGRAM] Could not init: {e}")
            
            # Start WebSocket for real-time prices
            try:
                from src.data.binance_websocket import start_websocket, get_websocket
                self.websocket = await start_websocket()
                self.logger.info("[WS] WebSocket started for real-time prices")
            except Exception as e:
                self.logger.warning(f"[WS] Could not start WebSocket: {e}")
            
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Start all enabled modules
            tasks = []
            for name, module in self.modules.items():
                if module is not None:
                    self.logger.info(f"[RUN]  Starting {name}...")
                    task = asyncio.create_task(module.run())
                    tasks.append(task)
            
            self.logger.info("[OK] All modules started")
            self.logger.info("[BOT] Cryptobot is now running!")
            
            # Start REAL training system in simulation mode
            if settings.SIMULATION_MODE:
                try:
                    from src.trading.real_trainer import start_real_training
                    asyncio.create_task(start_real_training())
                    self.logger.info("[TRAIN] REAL training system started (historical data + ML)")
                except Exception as e:
                    self.logger.warning(f"[TRAIN] Could not start real training: {e}")
                    # Fallback to simple simulator
                    try:
                        from src.trading.training_simulator import start_training
                        asyncio.create_task(start_training(interval_seconds=30))
                        self.logger.info("[TRAIN] Fallback to simple training simulator")
                    except Exception as e:
                        self.logger.debug(f"[TRAIN] Fallback training also failed: {e}")
            
            # Start Momentum Detector for active trading opportunities
            try:
                from src.modules.momentum_detector import MomentumDetector
                from src.trading.paper_trader import get_paper_trader
                
                self.momentum_detector = MomentumDetector()
                paper_trader = get_paper_trader()
                
                # Initialize paper trader
                await paper_trader.initialize()
                
                # Track last trade time to enforce minimum interval
                self._last_trade_time = None
                MIN_TRADE_INTERVAL_SECONDS = 120  # At least 2 minutes between trades
                
                # Connect momentum signals to paper trader with ULTRA-SMART filtering
                async def on_momentum_signal(signal):
                    """Trade on momentum signals - ULTRA OPTIMIZED with FULL Technical Analysis
                    
                    FILTRES AVANCÉS:
                    - Score minimum 55/100 (basé sur TOUS les indicateurs)
                    - MACD doit être bullish ou neutral
                    - EMA trend aligné (bullish ou neutral)
                    - BTC correlation positive (trade avec le marché)
                    - RSI entre 25-70 (pas surachat/survente extrême)
                    - Stochastic RSI sous 80 (pas surachat)
                    - ATR < 10% (volatilité contrôlée)
                    - Maximum 5 positions STRICTEMENT
                    """
                    try:
                        # === FILTRES DE SÉCURITÉ ===
                        
                        # 0. Enforce minimum time between trades (avoid over-trading)
                        now = datetime.utcnow()
                        if self._last_trade_time:
                            seconds_since_last = (now - self._last_trade_time).total_seconds()
                            if seconds_since_last < MIN_TRADE_INTERVAL_SECONDS:
                                self.logger.debug(f"[TRADE] Skip {signal.symbol} - too soon since last trade ({seconds_since_last:.0f}s < {MIN_TRADE_INTERVAL_SECONDS}s)")
                                return
                        
                        # 1. Vérifier STRICTEMENT qu'on n'a pas trop de positions
                        MAX_POSITIONS = 5
                        if len(paper_trader.portfolio.positions) >= MAX_POSITIONS:
                            self.logger.debug(f"[TRADE] Skip {signal.symbol} - max positions reached ({MAX_POSITIONS})")
                            return
                        
                        # 2. Éviter les tokens déjà en position
                        if signal.symbol in paper_trader.portfolio.positions:
                            return
                        
                        # === SWING TRADE STRATEGY v7.0 - BACKTEST ALIGNED ===
                        # CRITICAL FIX: Use EXACTLY the same filters as backtest (94.7% win rate)
                        # Previous version added filters NOT validated in backtest = bad results
                        #
                        # BACKTEST VALIDATED ONLY:
                        # 1. 24h change: 5-30%
                        # 2. RSI < 50 (STRICT)
                        # 3. Volume > $500k
                        # 4. Pullback 3-12% from high (checked in momentum_detector)
                        # 5. BTC not dumping > 1%
                        #
                        # REMOVED (not in backtest): MACD, EMA, StochRSI, ATR, Score, ML
                        
                        # --- BACKTEST VALIDATED FILTERS ONLY ---
                        
                        # 1. RSI: Back to backtest value for more trades
                        # Was < 45 (too strict), now < 50 (backtest validated)
                        rsi_ok = signal.rsi < 50  # Don't buy above RSI 50
                        
                        # 2. Volume: $500k minimum (from backtest)
                        min_volume = 500000
                        volume_ok = signal.volume_usd >= min_volume
                        
                        # 3. Change percent: Strong pump required (from backtest)
                        change_ok = 5.0 <= signal.change_percent <= 30.0
                        
                        # 4. BTC Correlation: Trade WITH the market (from backtest)
                        btc_ok = signal.btc_correlation > 0
                        
                        # 5. Basic score filter (relaxed for more trades)
                        MIN_SCORE = 50  # Lowered from 60 for more opportunities
                        has_good_score = signal.score >= MIN_SCORE
                        
                        # === DECISION - BACKTEST ALIGNED ===
                        should_trade = (
                            rsi_ok and
                            volume_ok and
                            change_ok and
                            btc_ok and
                            has_good_score
                        )
                        
                        # === CORRELATION CHECK ===
                        # Avoid too many correlated positions
                        btc_correlated = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
                        correlated_count = sum(1 for pos in paper_trader.portfolio.positions if pos in btc_correlated)
                        if signal.symbol in btc_correlated and correlated_count >= 3:
                            should_trade = False  # Max 3 BTC-correlated positions
                        
                        # === ML DISABLED - Was trained on bad data (40.9% win rate) ===
                        # Will be re-enabled after collecting good trades with new filters
                        # TODO: Reset ML data and retrain after 50+ trades with new filters
                        
                        if should_trade:
                            self.logger.info(f"[SWING] 🎯 Signal VALIDÉ: {signal.symbol} (Score: {signal.score:.0f}/100)")
                            self.logger.info(
                                f"[SWING]   24h: +{signal.change_percent:.1f}% | "
                                f"Vol: ${signal.volume_usd/1000000:.1f}M | RSI: {signal.rsi:.0f} | "
                                f"MACD: {signal.macd_signal}"
                            )
                            
                            # SWING TRADE SL - from backtest: SL=5% gives 94.7% win rate
                            base_sl = 0.05  # 5% default (backtest validated)
                            if signal.atr_percent > 0:
                                # Use 1.5x ATR as stop-loss, but minimum 4%, maximum 6%
                                dynamic_sl = max(0.04, min(0.06, signal.atr_percent * 1.5 / 100))
                            else:
                                dynamic_sl = base_sl
                            
                            # Prepare signal features for ML learning
                            signal_features = {
                                "signal_type": signal.signal_type,
                                "score": signal.score,
                                "change_percent": signal.change_percent,
                                "volume_usd": signal.volume_usd,
                                "rsi": signal.rsi,
                                "stoch_rsi": signal.stoch_rsi,
                                "macd_signal": signal.macd_signal,
                                "ema_trend": signal.ema_trend,
                                "atr_percent": signal.atr_percent,
                                "btc_correlation": signal.btc_correlation,
                                "volatility_24h": getattr(signal, 'volatility', 0)
                            }
                            
                            # Execute buy with dynamic stop-loss and ML features
                            position = await paper_trader.buy(
                                symbol=signal.symbol,
                                price=signal.price,
                                reason=f"Full TA: {signal.signal_type} Score:{signal.score:.0f} MACD:{signal.macd_signal}",
                                stop_loss_pct=dynamic_sl,
                                signal_features=signal_features
                            )
                            
                            if position:
                                self.logger.info(f"[TRADE] ✅ Acheté {signal.symbol} @ ${signal.price:.6f} (SL: {dynamic_sl*100:.1f}%)")
                                self.total_trades += 1
                                
                                # Update last trade time (enforce minimum interval)
                                self._last_trade_time = datetime.utcnow()
                                
                                self.momentum_detector.set_token_cooldown(signal.symbol)
                            else:
                                self.logger.warning(f"[TRADE] ❌ Échec achat {signal.symbol}")
                        else:
                            # Log pourquoi on skip (backtest-aligned filters only)
                            reasons = []
                            if not rsi_ok:
                                reasons.append(f"RSI={signal.rsi:.0f} (>50)")
                            if not volume_ok:
                                reasons.append(f"Vol=${signal.volume_usd/1000:.0f}k (<$500k)")
                            if not change_ok:
                                reasons.append(f"24h={signal.change_percent:.1f}%")
                            if not btc_ok:
                                reasons.append("BTC bearish")
                            if not has_good_score:
                                reasons.append(f"score={signal.score:.0f} (<{MIN_SCORE})")
                            
                            if reasons:
                                self.logger.debug(f"[TRADE] Skip {signal.symbol}: {', '.join(reasons)}")
                            
                    except Exception as e:
                        self.logger.error(f"[MOMENTUM] Trade error: {e}")
                
                self.momentum_detector.on_signal(on_momentum_signal)
                asyncio.create_task(self.momentum_detector.start())
                
                # Start position manager to auto-sell based on SL/TP
                async def manage_positions():
                    """Auto-manage positions - check SL/TP every 30 seconds + force close excess"""
                    import aiohttp
                    MAX_POSITIONS = 5
                    
                    while self.is_running:
                        try:
                            # FORCE CLOSE excess positions (keep only MAX_POSITIONS)
                            if len(paper_trader.portfolio.positions) > MAX_POSITIONS:
                                # Sort by PnL to close worst performers first
                                positions_with_pnl = []
                                async with aiohttp.ClientSession() as session:
                                    url = "https://api.binance.com/api/v3/ticker/price"
                                    async with session.get(url, timeout=10) as response:
                                        if response.status == 200:
                                            prices_data = await response.json()
                                            prices = {p['symbol']: float(p['price']) for p in prices_data}
                                            
                                            for symbol, pos in paper_trader.portfolio.positions.items():
                                                current = prices.get(symbol, pos.entry_price)
                                                pnl_pct = ((current - pos.entry_price) / pos.entry_price) * 100
                                                positions_with_pnl.append((symbol, pnl_pct, current))
                                
                                # Sort by PnL (worst first)
                                positions_with_pnl.sort(key=lambda x: x[1])
                                
                                # Close excess positions (worst performers)
                                excess = len(paper_trader.portfolio.positions) - MAX_POSITIONS
                                for i in range(excess):
                                    symbol, pnl, price = positions_with_pnl[i]
                                    self.logger.warning(f"[FORCE] Closing excess position {symbol} (PnL: {pnl:+.2f}%)")
                                    await paper_trader.sell(symbol, price, f"Force close: excess position (max={MAX_POSITIONS})")
                            
                            # Get current prices for all positions
                            if paper_trader.portfolio.positions:
                                async with aiohttp.ClientSession() as session:
                                    url = "https://api.binance.com/api/v3/ticker/price"
                                    async with session.get(url, timeout=10) as response:
                                        if response.status == 200:
                                            prices_data = await response.json()
                                            prices = {p['symbol']: float(p['price']) for p in prices_data}
                                            
                                            # Update prices and check SL/TP
                                            await paper_trader.update_prices(prices)
                                            
                                            # Log position status
                                            for symbol, pos in paper_trader.portfolio.positions.items():
                                                current = prices.get(symbol, pos.entry_price)
                                                pnl_pct = ((current - pos.entry_price) / pos.entry_price) * 100
                                                self.logger.info(f"[POS] {symbol}: Entry ${pos.entry_price:.6f} → Now ${current:.6f} ({pnl_pct:+.2f}%)")
                            
                            await asyncio.sleep(30)
                        except Exception as e:
                            self.logger.error(f"[POS] Position manager error: {e}")
                            await asyncio.sleep(60)
                
                asyncio.create_task(manage_positions())
                self.logger.info("[MOMENTUM] Momentum Detector started - detecting opportunities on existing cryptos")
                self.logger.info("[POSITIONS] Auto position manager started (SL/TP monitoring)")
            except Exception as e:
                self.logger.warning(f"[MOMENTUM] Could not start momentum detector: {e}")
            
            # ============ GECKOTERMINAL POOL DETECTOR + AI TRADING ENGINE ============
            # Detects new pools and trending tokens across DEXes with AI analysis
            try:
                from src.modules.geckoterminal.pool_detector import PoolDetector, PoolSignal
                from src.trading.dex_trader import DEXTrader
                from src.modules.ai.trading_engine import create_ai_trading_engine, TradeDecision
                
                pool_detector = PoolDetector()
                await pool_detector.initialize()
                
                # Initialize DEX trader for real trading
                dex_trader = DEXTrader()
                dex_initialized = await dex_trader.initialize()
                
                # Initialize AI Trading Engine
                try:
                    _capital = paper_trader.portfolio.initial_capital
                except Exception:
                    _capital = 10000
                ai_engine = create_ai_trading_engine(
                    web3_providers=dex_trader.providers if dex_initialized else {},
                    capital=_capital
                )
                self.logger.info("[AI] 🤖 AI Trading Engine initialized with all modules")
                
                # Initialize Safety Manager
                from src.core.safety_manager import get_safety_manager
                safety = get_safety_manager()
                safety_status = safety.get_status()
                self.logger.info(f"[SAFETY] Safety Manager initialized")
                self.logger.info(f"[SAFETY] Mode: {'SIMULATION' if safety.is_simulation_mode() else 'REAL'}")
                self.logger.info(f"[SAFETY] Sim trades: {safety_status['simulation']['trades']}/{safety.MIN_SIM_TRADES}")
                self.logger.info(f"[SAFETY] Real trading unlocked: {safety_status['safety']['real_trading_unlocked']}")
                self.logger.info(f"[SAFETY] Progress: {safety.get_progress_bar()}")

                # Wire safety events to Telegram notifications
                if hasattr(self, 'telegram') and self.telegram and self.telegram.is_enabled:
                    async def _safety_notifier(event_type: str, data: dict):
                        try:
                            if event_type == "mode_change":
                                await self.telegram.notify_mode_change(
                                    data["old_mode"], data["new_mode"], data.get("reason", ""))
                            elif event_type == "emergency_stop":
                                await self.telegram.notify_emergency_stop(data["reason"])
                            elif event_type == "emergency_unlock":
                                await self.telegram.notify_emergency_unlock()
                        except Exception as e:
                            self.logger.debug(f"[TELEGRAM] Safety notifier error: {e}")
                    safety.set_notifier(_safety_notifier)
                
                if dex_initialized:
                    if safety.is_simulation_mode():
                        self.logger.info("[DEX] DEX Trader ready (SIMULATION - no real money)")
                    else:
                        self.logger.info("[DEX] DEX Trader ready for REAL trading")
                else:
                    self.logger.info("[DEX] DEX Trader not initialized")
                
                import time as _time
                FUNDED_CHAINS = {"bsc", "base"}
                CAPITAL_ALLOCATION_MOMENTUM = 0.20  # 20% of capital for momentum
                _ai_cache = {}  # {token_addr: (timestamp, result)}
                AI_CACHE_TTL = 300  # 5 min
                _btc_price_cache = {"price": 0, "ts": 0}

                async def _is_btc_dumping() -> bool:
                    """Check if BTC is dumping (>3% drop in 1h). Skip momentum buys if so."""
                    try:
                        now = _time.time()
                        if now - _btc_price_cache["ts"] < 120:
                            return _btc_price_cache.get("dumping", False)
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=2", timeout=5) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if len(data) >= 2:
                                        prev_close = float(data[0][4])
                                        curr_close = float(data[1][4])
                                        change_pct = ((curr_close - prev_close) / prev_close) * 100
                                        is_dumping = change_pct < -3.0
                                        _btc_price_cache["price"] = curr_close
                                        _btc_price_cache["ts"] = now
                                        _btc_price_cache["dumping"] = is_dumping
                                        if is_dumping:
                                            self.logger.warning(f"[BTC] BTC dumping {change_pct:+.1f}% in 1h — blocking momentum buys")
                                        return is_dumping
                        _btc_price_cache["ts"] = now
                        _btc_price_cache["dumping"] = False
                        return False
                    except Exception:
                        return False
                
                _watchlist = {}
                _watchlist_lock = asyncio.Lock()
                _last_buy_time = [0]
                BUY_MIN_INTERVAL = 120  # 2 min between buys (fast for new tokens)
                WATCHLIST_MAX_AGE = 1800  # 30 min max
                WATCHLIST_MAX_SIZE = 50  # More tokens to watch = more opportunities
                MOMENTUM_CONFIRM_PCT = 8.0  # Enter earlier on confirmed momentum
                CONFIRMS_NEEDED = 3  # Fast entry (3 checks = ~90s of confirmation)
                HIGH_CONFIRM_THRESHOLD = 8  # Patient path with lower momentum
                HIGH_CONFIRM_MOMENTUM_PCT = 5.0  # Allow 5%+ with many confirms
                FAST_TRACK_PCT = 50.0  # Fast track if +50% surge
                CONFIRM_DIP_TOLERANCE = 3.0  # Allow small dips during confirmation
                MAX_VOLATILITY_PCT = 80.0  # New tokens are volatile, allow it
                MIN_MARKET_CAP_PROXY = 50_000  # $50k min estimated market cap (real mode)
                CREATOR_COOLDOWN_SECONDS = 3600  # 1h cooldown per pair/creator
                _creator_cooldowns = {}
                _price_fail_tokens = set()
                
                SCAM_EXACT_NAMES = {
                    "BITCOIN", "BTC", "ETH", "ETHEREUM", "BNB", "SOLANA", "SOL",
                    "XRP", "RIPPLE", "ADA", "CARDANO", "USDT", "USDC", "DAI",
                    "WETH", "WBTC", "LINK", "CHAINLINK", "AVAX", "AVALANCHE",
                    "MATIC", "POLYGON", "DOT", "POLKADOT", "UNI", "UNISWAP",
                    "AAVE", "CRV", "CURVE", "SUSHI", "COMP",
                    "TEST", "SCAM", "RUG", "FAIRLAUNCH", "SAFEMOON", "SAFEMARS",
                }
                SCAM_SUBSTRINGS = [
                    "ELON", "ELONMUSK", "TRUMP", "MAGA",
                    "FREE", "AIRDROP", "100X", "1000X",
                    "REWARD", "REFLEC", "REBASE", "ELASTIC",
                    "PONZI", "RUGPULL", "GIVEAWAY", "PRESALE",
                ]
                
                async def on_pool_signal(signal: PoolSignal):
                    """Step 1: Detect tokens and add to WATCHLIST (don't buy yet)"""
                    try:
                        pool = signal.pool
                        is_sim = safety.is_simulation_mode()
                        
                        if pool.network not in FUNDED_CHAINS:
                            self.logger.debug(f"[FILTER] {pool.base_token} rejected: network {pool.network} not funded")
                            return
                        if pool.address in _watchlist or pool.address in dex_trader.sniper_positions:
                            return
                        if len(_watchlist) >= WATCHLIST_MAX_SIZE:
                            self.logger.debug(f"[FILTER] {pool.base_token} rejected: watchlist full ({len(_watchlist)})")
                            return
                        
                        token_upper = pool.base_token.upper()
                        if token_upper in SCAM_EXACT_NAMES:
                            self.logger.debug(f"[FILTER] {pool.base_token} rejected: scam exact name")
                            return
                        for substr in SCAM_SUBSTRINGS:
                            if substr in token_upper:
                                self.logger.debug(f"[FILTER] {pool.base_token} rejected: scam substring '{substr}'")
                                return
                        
                        min_liq = 10_000 if is_sim else 15_000
                        min_vol = 5_000 if is_sim else 10_000
                        min_score = 30 if is_sim else 45
                        min_vlr = 0.1 if is_sim else 0.3
                        min_mcap = 20_000 if is_sim else 50_000
                        
                        if pool.liquidity_usd < min_liq:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: liq ${pool.liquidity_usd:,.0f} < ${min_liq:,.0f}")
                            return
                        if pool.volume_24h < min_vol:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: vol ${pool.volume_24h:,.0f} < ${min_vol:,.0f}")
                            return
                        if signal.score < min_score:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: score {signal.score:.0f} < {min_score}")
                            return
                        vol_liq_ratio = pool.volume_24h / max(pool.liquidity_usd, 1)
                        if vol_liq_ratio < min_vlr:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: vol/liq {vol_liq_ratio:.2f} < {min_vlr}")
                            return
                        if pool.price_change_24h < -5:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: price change {pool.price_change_24h:.1f}%")
                            return
                        est_mcap = pool.liquidity_usd * 2
                        if est_mcap < min_mcap:
                            self.logger.info(f"[FILTER] {pool.base_token} rejected: est mcap ${est_mcap:,.0f} < ${min_mcap:,.0f}")
                            return
                        
                        # Check creator/pair cooldown to avoid repeated rug-pulls
                        pair_key = pool.address
                        if pair_key in _creator_cooldowns:
                            if _time.time() - _creator_cooldowns[pair_key] < CREATOR_COOLDOWN_SECONDS:
                                return
                        
                        # ADD TO WATCHLIST — don't buy yet!
                        _watchlist[pool.address] = {
                            "symbol": pool.base_token,
                            "network": pool.network,
                            "address": pool.address,
                            "detect_price": pool.price_usd,
                            "detect_time": _time.time(),
                            "score": signal.score,
                            "liquidity": pool.liquidity_usd,
                            "volume": pool.volume_24h,
                            "confirm_count": 0,
                            "last_price": pool.price_usd,
                            "price_history": [pool.price_usd],
                            "peak_price": pool.price_usd,
                            "pair_key": pair_key,
                        }
                        self.logger.info(f"[WATCH] 👁️ Added {pool.base_token} to watchlist @ ${pool.price_usd:.8f} (score:{signal.score:.0f} liq:${pool.liquidity_usd:,.0f} vol:${pool.volume_24h:,.0f})")
                        self.logger.info(f"[WATCH] Watchlist: {len(_watchlist)} tokens | Waiting for +{MOMENTUM_CONFIRM_PCT}% momentum to buy")

                        try:
                            if hasattr(self, 'telegram') and self.telegram and self.telegram.is_enabled:
                                await self.telegram.notify_watchlist_add(
                                    symbol=pool.base_token,
                                    change_pct=pool.price_change_24h,
                                    liquidity=pool.liquidity_usd,
                                    score=signal.score,
                                )
                        except Exception:
                            pass

                    except Exception as e:
                        self.logger.error(f"[WATCH] Signal handler error: {e}")
                
                async def check_watchlist():
                    """Check watchlist with parallel price fetches and improved confirmation."""
                    while self.is_running:
                        try:
                            await asyncio.sleep(30)
                            
                            async with _watchlist_lock:
                                if not _watchlist:
                                    continue
                                snapshot = dict(_watchlist)
                            
                            now = _time.time()
                            symbols = [t["symbol"] for t in snapshot.values()]
                            self.logger.info(f"[WATCH] Checking {len(snapshot)} tokens: {', '.join(symbols[:10])}")
                            
                            # Fetch all prices concurrently
                            async def _fetch_price(addr, tok):
                                p = await dex_trader._get_token_price(tok["network"], addr)
                                return addr, p
                            
                            price_tasks = [_fetch_price(a, t) for a, t in snapshot.items()]
                            price_results = await asyncio.gather(*price_tasks, return_exceptions=True)
                            price_map = {}
                            for r in price_results:
                                if isinstance(r, Exception):
                                    continue
                                a, p = r
                                if p and p > 0:
                                    price_map[a] = p
                            
                            to_remove = []
                            
                            for addr, token in snapshot.items():
                                age = now - token["detect_time"]
                                
                                if age > WATCHLIST_MAX_AGE:
                                    self.logger.info(f"[WATCH] Expired: {token['symbol']} ({age/60:.0f}min)")
                                    to_remove.append(addr)
                                    continue
                                
                                if addr in dex_trader.sniper_positions:
                                    to_remove.append(addr)
                                    continue
                                
                                if now - _last_buy_time[0] < BUY_MIN_INTERVAL:
                                    continue
                                
                                # Consecutive loss cooldown
                                in_cooldown, cd_remaining = safety.is_in_cooldown()
                                if in_cooldown:
                                    self.logger.info(f"[WATCH] ⏸️ Cooldown active ({cd_remaining/60:.0f}min), skipping {token['symbol']}")
                                    continue
                                
                                if len(dex_trader.sniper_positions) >= 5:
                                    continue
                                
                                current_price = price_map.get(addr)
                                if not current_price:
                                    continue
                                
                                price_change_pct = ((current_price - token["detect_price"]) / token["detect_price"]) * 100
                                
                                # Track price history for volatility analysis
                                token.setdefault("price_history", []).append(current_price)
                                if current_price > token.get("peak_price", token["detect_price"]):
                                    token["peak_price"] = current_price
                                
                                # Volatility check: reject tokens with wild price swings (pump-dump pattern)
                                if len(token["price_history"]) >= 3:
                                    ph = token["price_history"]
                                    min_p, max_p = min(ph), max(ph)
                                    if min_p > 0:
                                        volatility = ((max_p - min_p) / min_p) * 100
                                        if volatility > MAX_VOLATILITY_PCT:
                                            self.logger.info(f"[WATCH] 🚫 Removed {token['symbol']}: volatility {volatility:.0f}% > {MAX_VOLATILITY_PCT}% (pump-dump)")
                                            to_remove.append(addr)
                                            continue
                                
                                # FIX: Confirm logic — price must be ABOVE detect_price AND increasing
                                # Old logic counted confirms even when price was below detect_price
                                above_detect = current_price > token["detect_price"]
                                increasing = current_price >= token["last_price"]
                                
                                if above_detect and increasing:
                                    token["confirm_count"] = token.get("confirm_count", 0) + 1
                                elif not above_detect:
                                    token["confirm_count"] = 0
                                else:
                                    dip_pct = ((token["last_price"] - current_price) / token["last_price"]) * 100
                                    if dip_pct > CONFIRM_DIP_TOLERANCE:
                                        token["confirm_count"] = max(0, token["confirm_count"] - 2)
                                
                                token["last_price"] = current_price
                                
                                self.logger.info(f"[WATCH] {token['symbol']}: {price_change_pct:+.1f}% ({age/60:.0f}min) | confirms: {token['confirm_count']}/{CONFIRMS_NEEDED}")
                                
                                fast_track = price_change_pct >= FAST_TRACK_PCT
                                confirmed = (price_change_pct >= MOMENTUM_CONFIRM_PCT and token["confirm_count"] >= CONFIRMS_NEEDED)
                                high_confirm = (token["confirm_count"] >= HIGH_CONFIRM_THRESHOLD and price_change_pct >= HIGH_CONFIRM_MOMENTUM_PCT)
                                
                                if confirmed or fast_track or high_confirm:
                                    # BTC trend gate: skip if BTC is crashing
                                    if await _is_btc_dumping():
                                        self.logger.info(f"[WATCH] BTC dump detected, skipping {token['symbol']}")
                                        continue
                                    
                                    mode_str = "FAST-TRACK" if fast_track else ("HIGH-CONFIRM" if high_confirm else "CONFIRMED")
                                    self.logger.info(f"[WATCH] {mode_str}: {token['symbol']} UP {price_change_pct:+.1f}%")
                                    self.logger.info(f"[WATCH]    Detect: ${token['detect_price']:.8f} → Now: ${current_price:.8f}")
                                    
                                    # AI analysis before buying
                                    chain_map = {"eth": "ethereum", "bsc": "bsc", "arbitrum": "arbitrum", "base": "base"}
                                    chain = chain_map.get(token["network"], token["network"])
                                    try:
                                        _ai_capital = paper_trader.portfolio.initial_capital
                                    except Exception:
                                        _ai_capital = 10000
                                    
                                    # Use AI cache to avoid re-analysis
                                    cached = _ai_cache.get(addr)
                                    if cached and (now - cached[0]) < AI_CACHE_TTL:
                                        ai_result = cached[1]
                                    else:
                                        ai_result = await ai_engine.analyze_token(
                                            token_address=addr,
                                            token_symbol=token["symbol"],
                                            chain=chain,
                                            current_price=current_price,
                                            liquidity_usd=token["liquidity"],
                                            volume_24h=token["volume"],
                                            capital=_ai_capital
                                        )
                                        _ai_cache[addr] = (now, ai_result)
                                    
                                    should_buy, reason = ai_engine.should_buy(ai_result)
                                    if not should_buy:
                                        self.logger.warning(f"[AI] ❌ {token['symbol']} momentum OK but AI blocked: {reason}")
                                        try:
                                            if hasattr(self, 'telegram') and self.telegram and self.telegram.is_enabled:
                                                await self.telegram.notify_ai_block(
                                                    symbol=token['symbol'],
                                                    reason=reason,
                                                    change_pct=price_change_pct,
                                                )
                                        except Exception:
                                            pass
                                        to_remove.append(addr)
                                        continue
                                    
                                    self.logger.info(f"[AI] ✅ {token['symbol']} APPROVED (confidence: {ai_result.confidence:.2f})")
                                    
                                    # Risk-based position sizing: risk 1% of capital per trade
                                    # Size = (capital * risk%) / stop_loss%
                                    RISK_PER_TRADE_PCT = 2.0
                                    sl_pct_val = 20.0  # matching the sniper_buy sl_pct
                                    if safety.is_simulation_mode():
                                        capital = paper_trader.portfolio.initial_capital if hasattr(paper_trader, 'portfolio') else 10000
                                        position_size = (capital * RISK_PER_TRADE_PCT / 100) / (sl_pct_val / 100)
                                        position_size = min(position_size, 50.0)  # cap at $50 in sim
                                    elif dex_initialized:
                                        _, available_usd = dex_trader.get_available_capital(token["network"])
                                        momentum_budget = available_usd * CAPITAL_ALLOCATION_MOMENTUM
                                        risk_sized = (available_usd * RISK_PER_TRADE_PCT / 100) / (sl_pct_val / 100)
                                        position_size = min(risk_sized, momentum_budget * 0.5, safety.MAX_TRADE_USD)
                                        if position_size < 2:
                                            continue
                                    else:
                                        position_size = ai_result.recommended_amount_usd
                                    
                                    trade = await dex_trader.sniper_buy(
                                        network=token["network"],
                                        token_address=addr,
                                        amount_usd=position_size,
                                        token_symbol=token["symbol"],
                                        tp1_pct=30.0,
                                        tp2_pct=75.0,
                                        tp3_pct=150.0,
                                        sl_pct=20.0,
                                        max_hold_hours=0.5
                                    )
                                    if trade:
                                        safety.record_buy(
                                            token=token["symbol"],
                                            network=token["network"],
                                            amount_usd=position_size,
                                            price=trade.price_usd,
                                            is_sim=safety.is_simulation_mode()
                                        )
                                        _last_buy_time[0] = now
                                        _creator_cooldowns[token.get("pair_key", "")] = now
                                        self.logger.info(f"[TRADE] BOUGHT {token['symbol']} after +{price_change_pct:.1f}% momentum | {safety.get_progress_bar()}")
                                        self.total_trades += 1
                                        try:
                                            if hasattr(self, 'telegram') and self.telegram.is_enabled:
                                                await self.telegram.notify_trade_opened(
                                                    symbol=token["symbol"], side="BUY",
                                                    price=trade.price_usd, amount=position_size,
                                                    reason=f"{mode_str} +{price_change_pct:.1f}%")
                                        except Exception:
                                            pass
                                    to_remove.append(addr)
                                
                                # Token dumping from detection price — remove early
                                elif price_change_pct < -10:
                                    self.logger.info(f"[WATCH] 📉 Removed {token['symbol']}: dropped {price_change_pct:+.1f}% since detection")
                                    to_remove.append(addr)
                            
                            async with _watchlist_lock:
                                for addr in to_remove:
                                    _watchlist.pop(addr, None)
                            
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            self.logger.error(f"[WATCH] Watchlist check error: {e}")
                            await asyncio.sleep(10)
                
                # Task to periodically check sniper positions for TP/SL
                async def sniper_monitor_loop():
                    """Monitor sniper positions every 10 seconds for fast SL reaction on new tokens"""
                    _loop_count = 0
                    while self.is_running:
                        try:
                            _loop_count += 1
                            await dex_trader.check_sniper_positions()
                            await asyncio.sleep(10)
                        except Exception as e:
                            self.logger.error(f"[SNIPER] Monitor error: {e}")
                            await asyncio.sleep(10)
                
                pool_detector.on_signal(on_pool_signal)
                asyncio.create_task(pool_detector.start())
                asyncio.create_task(sniper_monitor_loop())
                asyncio.create_task(check_watchlist())
                
                # ============ GRID TRADING ENGINE (PRIMARY STRATEGY) ============
                try:
                    from src.trading.grid_trader import GridTrader
                    _tg = self.telegram if hasattr(self, 'telegram') else None
                    grid_trader = GridTrader(dex_trader=dex_trader, safety_manager=safety, telegram=_tg)
                    await grid_trader.initialize()
                    asyncio.create_task(grid_trader.run())
                    self.grid_trader = grid_trader
                    self.logger.info("[GRID] ✅ Grid Trading Engine started (PRIMARY strategy)")
                except Exception as e:
                    self.logger.error(f"[GRID] Grid Trading init error: {e}")
                    grid_trader = None
                
                self.logger.info("=" * 60)
                self.logger.info("[STRATEGY] DUAL STRATEGY ACTIVE:")
                self.logger.info("[STRATEGY]   1. REGIME-ADAPTIVE GRID on ETH/USDC + BNB/USDT (80% capital)")
                self.logger.info("[STRATEGY]   2. NEW TOKEN SNIPER on BSC + Base (20% capital)")
                self.logger.info(f"[STRATEGY]   Sniper: +{MOMENTUM_CONFIRM_PCT}% + {CONFIRMS_NEEDED} confirms | TP 30/75/150% | SL 20% | MaxHold 30min")
                self.logger.info(f"[STRATEGY]   Max {5} positions | Check every 30s | BTC trend gate | Min liq $10k")
                self.logger.info("=" * 60)
                self.logger.info("[AI]   ✓ Position Sizer - Dynamic risk management")
                self.logger.info("[AI]   ✓ DEX Aggregator - Best price routing")
                self.logger.info("[AI]   ✓ Whale Tracker - Big money detection")
                
            except Exception as e:
                self.logger.warning(f"[GECKO] Could not start pool detector: {e}")
            
            # Start Market Data Aggregator (CoinGecko + LunarCrush) - DISABLED due to bugs
            # The market aggregator was causing issues:
            # 1. Buying tokens without technical analysis
            # 2. XMRUSDT and LITUSDT stuck at wrong prices
            # 3. Too many force-closes due to excess positions
            #
            # SOLUTION: Disabled until we implement proper filtering
            # Only use the Momentum Detector which has proper TA filters
            self.logger.info("[MARKET] Market Aggregator DISABLED (using only Momentum Detector with TA filters)")
            
            # Main loop - monitor and coordinate
            await self._main_loop()
            
        except Exception as e:
            self.logger.error(f"[ERROR] Fatal error: {e}")
            await self.stop()
            raise
    
    async def _main_loop(self):
        """Main orchestrator loop"""
        import time as _t
        _last_daily_report = _t.time()
        DAILY_REPORT_INTERVAL = 3600 * 6  # Every 6 hours

        while self.is_running:
            try:
                await self._health_check()
                await self._update_metrics()
                await self.risk_manager.check_global_limits()

                # Periodic Telegram report
                now = _t.time()
                if now - _last_daily_report > DAILY_REPORT_INTERVAL:
                    _last_daily_report = now
                    await self._send_telegram_report()

                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def _send_telegram_report(self):
        if not hasattr(self, 'telegram') or not self.telegram or not self.telegram.is_enabled:
            return
        try:
            from src.core.safety_manager import get_safety_manager
            safety = get_safety_manager()
            status = safety.get_status()
            sim = status["simulation"]
            grid = status["grid"]
            mom = status["momentum"]
            mode = status["safety"]["current_mode"]

            uptime_h = 0
            if self.start_time:
                uptime_h = (datetime.utcnow() - self.start_time).total_seconds() / 3600

            grid_info = ""
            if self.grid_trader:
                gs = self.grid_trader.get_status()
                grid_info = (
                    f"\n\n📊 <b>Grid Trading</b>\n"
                    f"Cycles: {gs['total_cycles']} | WR: {gs['win_rate']} | P&L: {gs['total_pnl']}\n"
                    f"Rate: {gs.get('profit_per_day', 'N/A')}"
                )

            msg = (
                f"📈 <b>Rapport Cryptobot</b>\n\n"
                f"⏱ Uptime: {uptime_h:.1f}h | Mode: <b>{mode}</b>\n"
                f"💹 Trades: {self.total_trades}\n\n"
                f"🧪 <b>Simulation</b>\n"
                f"Trades: {sim['trades']} | WR: {sim['win_rate']} | P&L: {sim['total_pnl']}\n"
                f"Grid: {grid['trades']}t WR {grid['win_rate']} | Mom: {mom['trades']}t WR {mom['win_rate']}"
                f"{grid_info}\n\n"
                f"<i>{datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC</i>"
            )
            await self.telegram.send_message(msg)
        except Exception as e:
            self.logger.warning(f"[TELEGRAM] Report error: {e}")
    
    async def _health_check(self):
        """Perform health check on all components"""
        # Check database connection
        if self.database:
            if not await self.database.is_healthy():
                self.logger.warning("[WARN]  Database health check failed")
        
        # Check each module
        for name, module in self.modules.items():
            if module is not None:
                try:
                    if not await module.is_healthy():
                        self.logger.warning(f"[WARN]  {name} health check failed")
                except Exception as e:
                    self.logger.error(f"[ERROR] {name} health check error: {e}")
    
    async def _update_metrics(self):
        """Update system metrics and dashboard status"""
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            if int(uptime) % 300 == 0:
                self.logger.info(f"[INFO] Uptime: {uptime/3600:.2f}h | Trades: {self.total_trades} | PnL: ${self.total_pnl:.2f}")

        # Update healthcheck dashboard with active modules
        try:
            from src.healthcheck import update_status
            active_modules = []
            for name, module in self.modules.items():
                if module is not None:
                    active_modules.append(name)
            if hasattr(self, 'grid_trader') and self.grid_trader:
                active_modules.append("grid_trader")
            update_status(active_modules)
        except Exception:
            pass
    
    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            self.logger.info(f"[WARN]  Received signal {sig}, initiating shutdown...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def stop(self):
        """Gracefully stop all modules and cleanup"""
        if not self.is_running:
            return
        
        self.logger.info("[STOP] Stopping Cryptobot...")
        self.is_running = False
        
        try:
            # Stop all modules
            for name, module in self.modules.items():
                if module is not None:
                    try:
                        self.logger.info(f"[STOP]  Stopping {name}...")
                        await module.stop()
                    except Exception as e:
                        self.logger.error(f"Error stopping {name}: {e}")
            
            # Close database connection
            if self.database:
                await self.database.disconnect()
                self.logger.info("[OK] Database disconnected")
            
            # Final statistics
            if self.start_time:
                runtime = (datetime.utcnow() - self.start_time).total_seconds()
                self.logger.info(f"[INFO] Final Stats:")
                self.logger.info(f"   Runtime: {runtime/3600:.2f} hours")
                self.logger.info(f"   Total trades: {self.total_trades}")
                self.logger.info(f"   Total PnL: ${self.total_pnl:.2f}")
            
            self.logger.info("[OK] Shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current system status"""
        return {
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0,
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "enabled_modules": list(self.modules.keys()),
            "environment": settings.ENVIRONMENT.value,
            "testnet": settings.USE_TESTNET,
        }

