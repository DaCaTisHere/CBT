"""
Real Training System - Trains the bot on actual historical data

This is the REAL training that:
1. Collects actual historical listing data
2. Trains the ML model on real patterns
3. Backtests to validate performance
4. Continues learning from new data
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from src.trading.data_collector import RealDataCollector
from src.trading.ml_model import TradingMLModel
from src.trading.backtester import Backtester, run_full_backtest
from src.trading.paper_trader import get_paper_trader
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RealTrainer:
    """
    Real training system that learns from actual market data
    """
    
    def __init__(self):
        self.logger = logger
        self.data_collector = RealDataCollector()
        self.ml_model = TradingMLModel()
        self.backtester = Backtester()
        self.paper_trader = get_paper_trader()
        
        self.is_initialized = False
        self.training_stats: Dict[str, Any] = {}
        
    async def initialize(self):
        """Initialize all components"""
        self.logger.info("[REAL-TRAIN] Initializing real training system...")
        
        await self.data_collector.initialize()
        await self.ml_model.initialize()
        await self.paper_trader.initialize()
        
        self.is_initialized = True
        self.logger.info("[REAL-TRAIN] Real training system ready")
        
    async def run_initial_training(self) -> Dict[str, Any]:
        """
        Run initial training cycle:
        1. Collect all historical data
        2. Train ML model
        3. Run backtest
        4. Report results
        """
        if not self.is_initialized:
            await self.initialize()
        
        self.logger.info("=" * 60)
        self.logger.info("[REAL-TRAIN] STARTING INITIAL TRAINING")
        self.logger.info("=" * 60)
        
        results = {
            "started_at": datetime.utcnow().isoformat(),
            "data_collection": {},
            "ml_training": {},
            "backtest": {},
            "status": "running"
        }
        
        try:
            # Step 1: Collect historical data
            self.logger.info("[REAL-TRAIN] Step 1/3: Collecting historical data...")
            listings = await self.data_collector.collect_all_data()
            
            results["data_collection"] = {
                "total_listings": len(listings),
                "exchanges": list(set(l.exchange for l in listings)),
                "date_range": {
                    "from": min(l.listing_date for l in listings).isoformat() if listings else None,
                    "to": max(l.listing_date for l in listings).isoformat() if listings else None
                }
            }
            
            self.data_collector.print_statistics()
            
            if not listings:
                results["status"] = "failed"
                results["error"] = "No historical data collected"
                return results
            
            # Step 2: Train ML model
            self.logger.info("[REAL-TRAIN] Step 2/3: Training ML model...")
            training_data = self.data_collector.get_training_data()
            training_metrics = await self.ml_model.train(training_data)
            
            results["ml_training"] = {
                "samples": training_metrics.get("samples", 0),
                "profitable_rate": training_metrics.get("profitable_rate", 0),
                "avg_return": training_metrics.get("avg_return", 0),
                "model_info": self.ml_model.get_model_info()
            }
            
            # Step 3: Run backtest
            self.logger.info("[REAL-TRAIN] Step 3/3: Running backtest validation...")
            self.backtester.ml_model = self.ml_model
            self.backtester.data_collector = self.data_collector
            
            backtest_result = await self.backtester.run_backtest(listings)
            
            results["backtest"] = backtest_result.to_dict()
            
            # Final status
            if backtest_result.win_rate >= 50 and backtest_result.total_pnl > 0:
                results["status"] = "success"
                results["recommendation"] = "Model is profitable, ready for paper trading validation"
            else:
                results["status"] = "needs_improvement"
                results["recommendation"] = "Model needs more data or parameter tuning"
            
            results["completed_at"] = datetime.utcnow().isoformat()
            
            self.training_stats = results
            
            # Summary
            self._print_summary(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"[REAL-TRAIN] Training failed: {e}")
            results["status"] = "error"
            results["error"] = str(e)
            return results
    
    async def predict_listing(
        self,
        symbol: str,
        exchange: str,
        volume: float = 0,
        sentiment: float = 0.5,
        market_cap: float = 0
    ) -> Dict[str, Any]:
        """
        Use trained model to predict if a listing should be traded
        """
        if not self.ml_model.is_trained:
            self.logger.warning("[REAL-TRAIN] Model not trained yet!")
            return {"error": "Model not trained"}
        
        prediction = self.ml_model.predict(
            symbol=symbol,
            exchange=exchange,
            volume=volume,
            sentiment=sentiment,
            market_cap=market_cap
        )
        
        return {
            "symbol": prediction.symbol,
            "should_buy": prediction.should_buy,
            "confidence": prediction.confidence,
            "predicted_return": prediction.predicted_return,
            "risk_level": prediction.risk_level,
            "reasoning": prediction.reasoning
        }
    
    def _print_summary(self, results: Dict):
        """Print training summary"""
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("[REAL-TRAIN] TRAINING SUMMARY")
        self.logger.info("=" * 60)
        
        # Data
        data = results.get("data_collection", {})
        self.logger.info(f"  Historical listings: {data.get('total_listings', 0)}")
        self.logger.info(f"  Exchanges: {', '.join(data.get('exchanges', []))}")
        
        # ML
        ml = results.get("ml_training", {})
        self.logger.info(f"  ML samples: {ml.get('samples', 0)}")
        self.logger.info(f"  Profitable rate: {ml.get('profitable_rate', 0):.1f}%")
        
        # Backtest
        bt = results.get("backtest", {})
        self.logger.info(f"  Backtest trades: {bt.get('total_trades', 0)}")
        self.logger.info(f"  Backtest win rate: {bt.get('win_rate', 0):.1f}%")
        self.logger.info(f"  Backtest P&L: ${bt.get('total_pnl', 0):+,.2f}")
        
        # Status
        status = results.get("status", "unknown")
        if status == "success":
            self.logger.info("")
            self.logger.info("  *** MODEL IS READY FOR TRADING ***")
        elif status == "needs_improvement":
            self.logger.info("")
            self.logger.info("  *** MODEL NEEDS MORE DATA ***")
        
        self.logger.info("=" * 60)


async def start_real_training():
    """
    Start the real training process
    
    Called by orchestrator when in simulation mode
    """
    trainer = RealTrainer()
    
    try:
        # Run initial training
        results = await trainer.run_initial_training()
        
        if results.get("status") == "success":
            logger.info("[REAL-TRAIN] Initial training successful!")
            logger.info("[REAL-TRAIN] Bot will now use ML predictions for new listings")
            
            # Continue monitoring for new listings to add to training data
            await _continuous_learning_loop(trainer)
        else:
            logger.warning(f"[REAL-TRAIN] Training status: {results.get('status')}")
            logger.info("[REAL-TRAIN] Will retry training with more data...")
            
            # Still run the learning loop to collect more data
            await _continuous_learning_loop(trainer)
            
    except Exception as e:
        logger.error(f"[REAL-TRAIN] Error: {e}")


async def _continuous_learning_loop(trainer: RealTrainer):
    """
    Continuous learning loop - checks for new listings
    and retrains periodically
    """
    retrain_interval = 3600 * 6  # Retrain every 6 hours
    last_retrain = datetime.utcnow()
    
    while True:
        try:
            # Check if time to retrain
            if (datetime.utcnow() - last_retrain).total_seconds() > retrain_interval:
                logger.info("[REAL-TRAIN] Scheduled retraining...")
                await trainer.run_initial_training()
                last_retrain = datetime.utcnow()
            
            # Sleep before next check
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except asyncio.CancelledError:
            logger.info("[REAL-TRAIN] Training loop stopped")
            break
        except Exception as e:
            logger.error(f"[REAL-TRAIN] Loop error: {e}")
            await asyncio.sleep(60)

