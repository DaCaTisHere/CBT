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

# Import trading mode manager for preflight checks
try:
    from src.core.trading_mode import get_trading_mode_manager
    TRADING_MODE_AVAILABLE = True
except ImportError as e:
    TRADING_MODE_AVAILABLE = False
    logger.warning(f"Trading mode manager not available: {e}")


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
    
    # Confirm if production mode (skip on Railway/Docker - no interactive input)
    if settings.is_production() and not settings.USE_TESTNET and not os.getenv("RAILWAY_ENVIRONMENT"):
        try:
            confirm = input("\n[WARN]  PRODUCTION MODE with REAL MONEY. Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("Aborted by user")
                return
        except EOFError:
            pass  # Non-interactive environment
    
    try:
        orchestrator = Orchestrator()
        
        if duration:
            logger.info(f"[TIMER] Running for {duration} seconds...")
            asyncio.run(run_with_duration(orchestrator, duration))
        else:
            asyncio.run(run_with_autonomous(orchestrator))
            
    except KeyboardInterrupt:
        logger.info("[STOP] Interrupted by user")
    except Exception as e:
        logger.error(f"[FATAL] Fatal error: {e}", exc_info=True)
        sys.exit(1)


async def run_with_autonomous(orchestrator: Orchestrator):
    """Run orchestrator"""
    try:
        if TRADING_MODE_AVAILABLE and not settings.SIMULATION_MODE and not settings.DRY_RUN:
            trading_mode = get_trading_mode_manager()
            logger.info("")
            logger.warning("⚠️  REAL TRADING MODE DETECTED - Running preflight checks...")
            
            all_passed, results = await trading_mode.run_preflight_checks()
            
            if not all_passed:
                logger.error("❌ PREFLIGHT CHECKS FAILED - Cannot start real trading")
                logger.error("   Fix the issues above or switch to SIMULATION_MODE=true")
                logger.info(trading_mode.get_mode_switch_instructions())
                raise SystemExit("Preflight checks failed")
            
            logger.info("✅ Preflight checks passed - Real trading enabled")
            logger.warning("💰 REAL MONEY IS AT RISK - Trade responsibly!")
            logger.info("")
        
        await orchestrator.start()
        
    except Exception as e:
        logger.error(f"[ERROR] Error in main loop: {e}", exc_info=True)
        raise


async def run_with_duration(orchestrator: Orchestrator, duration: int):
    """Run orchestrator for a specific duration"""
    try:
        task = asyncio.create_task(orchestrator.start())
        
        await asyncio.sleep(duration)
        
        logger.info("[TIMER] Duration reached, stopping...")
        await orchestrator.stop()
        
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
    logger.info(banner)


def display_config():
    """Display current configuration"""
    logger.info("[CONFIG] Configuration:")
    logger.info(f"   Environment: {settings.ENVIRONMENT.value}")
    logger.info(f"   Testnet: {settings.USE_TESTNET}")
    logger.info(f"   Simulation: {settings.SIMULATION_MODE}")
    logger.info(f"   Dry Run: {settings.DRY_RUN}")
    logger.info(f"   Log Level: {settings.LOG_LEVEL.value}")
    logger.info("")
    logger.info("")


if __name__ == "__main__":
    main()

