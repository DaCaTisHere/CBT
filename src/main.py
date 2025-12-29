"""
Cryptobot Ultimate - Main Entry Point

Usage:
    python src/main.py                    # Start with default settings
    python src/main.py --testnet          # Force testnet mode
    python src/main.py --simulation       # Simulation mode (no real trades)
    python src/main.py --mode test        # Test mode with duration
"""

import asyncio
import sys
import os
import click
from pathlib import Path

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    os.system("chcp 65001 > nul")
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator import Orchestrator
from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


@click.command()
@click.option('--testnet', is_flag=True, help='Force testnet mode')
@click.option('--simulation', is_flag=True, help='Simulation mode (no real trades)')
@click.option('--mode', type=click.Choice(['production', 'test', 'simulation']), 
              default='production', help='Running mode')
@click.option('--duration', type=int, default=None, 
              help='Run duration in seconds (for testing)')
def main(testnet: bool, simulation: bool, mode: str, duration: int):
    """
    Cryptobot Ultimate - Main Entry Point
    """
    # Display banner
    print_banner()
    
    # Override settings based on CLI arguments
    if testnet:
        settings.USE_TESTNET = True
        logger.info("[TEST] Testnet mode ENABLED via CLI")
    
    if simulation or mode == 'simulation':
        settings.SIMULATION_MODE = True
        logger.info("[SIM] Simulation mode ENABLED via CLI")
    
    # Display configuration
    display_config()
    
    # Confirm if production mode
    if settings.is_production() and not settings.USE_TESTNET:
        confirm = input("\n[WARN]  PRODUCTION MODE with REAL MONEY. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Aborted by user")
            return
    
    # Start orchestrator
    try:
        orchestrator = Orchestrator()
        
        if duration:
            # Run for specific duration (testing)
            logger.info(f"[TIMER] Running for {duration} seconds...")
            asyncio.run(run_with_duration(orchestrator, duration))
        else:
            # Run until interrupted
            asyncio.run(orchestrator.start())
            
    except KeyboardInterrupt:
        logger.info("[STOP] Interrupted by user")
    except Exception as e:
        logger.error(f"[FATAL] Fatal error: {e}", exc_info=True)
        sys.exit(1)


async def run_with_duration(orchestrator: Orchestrator, duration: int):
    """Run orchestrator for a specific duration"""
    try:
        # Start orchestrator in background
        task = asyncio.create_task(orchestrator.start())
        
        # Wait for duration
        await asyncio.sleep(duration)
        
        # Stop gracefully
        logger.info("[TIMER] Duration reached, stopping...")
        await orchestrator.stop()
        
        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
            
    except Exception as e:
        logger.error(f"Error during timed run: {e}")
        await orchestrator.stop()


def print_banner():
    """Print ASCII banner"""
    banner = """
    ============================================================
    ||                                                        ||
    ||               CRYPTOBOT ULTIMATE v0.1.0               ||
    ||                                                        ||
    ||          High Risk / High Reward Trading Bot          ||
    ||                                                        ||
    ============================================================
    """
    print(banner)


def display_config():
    """Display current configuration"""
    logger.info("[CONFIG] Configuration:")
    logger.info(f"   Environment: {settings.ENVIRONMENT.value}")
    logger.info(f"   Testnet: {settings.USE_TESTNET}")
    logger.info(f"   Simulation: {settings.SIMULATION_MODE}")
    logger.info(f"   Dry Run: {settings.DRY_RUN}")
    logger.info(f"   Log Level: {settings.LOG_LEVEL.value}")
    logger.info("")
    logger.info("[MODULES] Enabled Modules:")
    if settings.ENABLE_SNIPER:
        logger.info("   [OK] Sniper Bot")
    if settings.ENABLE_NEWS_TRADER:
        logger.info("   [OK] News Trader")
    if settings.ENABLE_SENTIMENT:
        logger.info("   [OK] Sentiment Analyzer")
    if settings.ENABLE_ML_PREDICTOR:
        logger.info("   [OK] ML Predictor")
    if settings.ENABLE_ARBITRAGE:
        logger.info("   [OK] Arbitrage Engine")
    if settings.ENABLE_DEFI_OPTIMIZER:
        logger.info("   [OK] DeFi Optimizer")
    if settings.ENABLE_COPY_TRADING:
        logger.info("   [OK] Copy Trading")
    logger.info("")


if __name__ == "__main__":
    main()

