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
                    except:
                        pass
            
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
                        
                        # === PULLBACK STRATEGY v5.0 FILTERS ===
                        
                        # Score minimum - HIGHER for quality over quantity
                        MIN_SCORE = 75  # Pullback signals are pre-filtered, use higher threshold
                        has_good_score = signal.score >= MIN_SCORE
                        
                        # MACD: Prefer bullish (momentum turning up on pullback)
                        macd_ok = signal.macd_signal in ["bullish", "neutral"]
                        
                        # EMA Trend: Uptrend should be intact
                        ema_ok = signal.ema_trend in ["bullish", "bullish_cross", "neutral"]
                        
                        # BTC Correlation: Trade WITH the market
                        btc_ok = signal.btc_correlation > 0
                        
                        # RSI: STRICT - not overbought (key for pullback entry)
                        rsi_ok = 25 <= signal.rsi <= 60  # Stricter upper limit for pullback
                        
                        # Stochastic RSI: STRICT - not overbought
                        stoch_ok = signal.stoch_rsi <= 65  # Stricter for pullback
                        
                        # ATR: Volatility controlled
                        atr_ok = signal.atr_percent <= 12 if signal.atr_percent > 0 else True
                        
                        # Volume: Higher requirement for pullback reliability
                        min_volume = 500000  # $500k minimum for pullback
                        volume_ok = signal.volume_usd >= min_volume
                        
                        # Change percent: Must have pumped (pullback requires prior pump)
                        change_ok = 3.0 <= signal.change_percent <= 20.0  # Pullback range
                        
                        # === PULLBACK DECISION ===
                        should_trade = (
                            has_good_score and
                            macd_ok and
                            ema_ok and
                            btc_ok and
                            rsi_ok and
                            stoch_ok and
                            atr_ok and
                            volume_ok and
                            change_ok
                        )
                        
                        # DISABLE volume_spike override - 0% success rate
                        # Pullback signals only from now on
                        
                        # === CORRELATION CHECK ===
                        # Avoid too many correlated positions (BTC-correlated coins)
                        btc_correlated = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
                        correlated_count = sum(1 for pos in paper_trader.portfolio.positions if pos in btc_correlated)
                        if signal.symbol in btc_correlated and correlated_count >= 3:
                            should_trade = False  # Max 3 BTC-correlated positions
                        
                        # === ML AUTO-LEARNING CHECK ===
                        # If the bot has learned enough, use predictions to filter trades
                        ml_approved = True
                        ml_confidence = 0.5
                        ML_CONFIDENCE_THRESHOLD = 0.58  # Balanced threshold
                        
                        if should_trade and paper_trader.auto_learner and paper_trader.auto_learner.is_trained:
                            ml_approved, ml_confidence, ml_reasons = paper_trader.auto_learner.predict_success(
                                signal_type=signal.signal_type,
                                signal_score=signal.score,
                                rsi=signal.rsi,
                                stoch_rsi=signal.stoch_rsi,
                                macd_signal=signal.macd_signal,
                                ema_trend=signal.ema_trend,
                                volume_usd=signal.volume_usd,
                                change_percent=signal.change_percent,
                                btc_correlation=signal.btc_correlation
                            )
                            
                            # Apply strict ML threshold
                            if not ml_approved or ml_confidence < ML_CONFIDENCE_THRESHOLD:
                                self.logger.info(f"[ML] 🧠 Blocked {signal.symbol} - ML confidence {ml_confidence*100:.0f}% < {ML_CONFIDENCE_THRESHOLD*100:.0f}%")
                                should_trade = False
                            else:
                                self.logger.debug(f"[ML] ✓ Approved {signal.symbol} ({ml_confidence*100:.0f}%)")
                        
                        if should_trade:
                            self.logger.info(f"[PULLBACK] 🎯 Signal VALIDÉ: {signal.symbol} (Score: {signal.score:.0f}/100)")
                            self.logger.info(
                                f"[PULLBACK]   24h: +{signal.change_percent:.1f}% | "
                                f"Vol: ${signal.volume_usd/1000000:.1f}M | RSI: {signal.rsi:.0f} | "
                                f"MACD: {signal.macd_signal}"
                            )
                            
                            # PULLBACK STRATEGY SL - tighter since we're entering at better price
                            # ATR-based SL is more adaptive to market volatility
                            base_sl = 0.03  # 3% default (tighter for pullback entry)
                            if signal.atr_percent > 0:
                                # Use 1.2x ATR as stop-loss, but minimum 2.5%, maximum 5%
                                dynamic_sl = max(0.025, min(0.05, signal.atr_percent * 1.2 / 100))
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
                                
                                # Set cooldown for this token
                                self.momentum_detector.set_token_cooldown(signal.symbol)
                                
                                # Notification Telegram
                                try:
                                    if hasattr(self, 'telegram') and self.telegram.is_enabled:
                                        await self.telegram.send_message(
                                            f"🟢 *ACHAT* {signal.symbol}\n"
                                            f"Prix: ${signal.price:.6f}\n"
                                            f"Score: {signal.score:.0f}/100\n"
                                            f"MACD: {signal.macd_signal} | EMA: {signal.ema_trend}\n"
                                            f"BTC: {'✓ Aligné' if signal.btc_correlation > 0 else '✗ Contre'}\n"
                                            f"SL: {dynamic_sl*100:.1f}%"
                                        )
                                except:
                                    pass
                            else:
                                self.logger.warning(f"[TRADE] ❌ Échec achat {signal.symbol}")
                        else:
                            # Log pourquoi on skip (seulement les plus importants)
                            reasons = []
                            if not has_good_score:
                                reasons.append(f"score={signal.score:.0f} (< {MIN_SCORE})")
                            if not btc_ok:
                                reasons.append("BTC bearish")
                            if not macd_ok:
                                reasons.append("MACD bearish")
                            if not ema_ok:
                                reasons.append("EMA bearish")
                            if not rsi_ok:
                                reasons.append(f"RSI={signal.rsi:.0f}")
                            
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
        while self.is_running:
            try:
                # Monitor system health
                await self._health_check()
                
                # Update metrics
                await self._update_metrics()
                
                # Check risk limits
                await self.risk_manager.check_global_limits()
                
                # Sleep for a bit
                await asyncio.sleep(10)
                
            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
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
        """Update system metrics"""
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            # Log metrics periodically
            if int(uptime) % 300 == 0:  # Every 5 minutes
                self.logger.info(f"[INFO] Uptime: {uptime/3600:.2f}h | Trades: {self.total_trades} | PnL: ${self.total_pnl:.2f}")
    
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

