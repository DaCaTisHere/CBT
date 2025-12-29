"""
Training Simulator - Automatic Paper Trading Training

Simulates market conditions and executes paper trades to train the bot.
"""

import asyncio
import random
from datetime import datetime
from typing import Dict, Any

from src.trading.paper_trader import get_paper_trader
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Simulated token listings (for training)
SIMULATED_LISTINGS = [
    {"symbol": "PEPE", "exchange": "binance", "type": "meme"},
    {"symbol": "WOJAK", "exchange": "binance", "type": "meme"},
    {"symbol": "FLOKI", "exchange": "binance", "type": "meme"},
    {"symbol": "SHIB", "exchange": "coinbase", "type": "meme"},
    {"symbol": "BONK", "exchange": "binance", "type": "meme"},
    {"symbol": "WIF", "exchange": "binance", "type": "meme"},
    {"symbol": "ARB", "exchange": "coinbase", "type": "defi"},
    {"symbol": "OP", "exchange": "binance", "type": "defi"},
    {"symbol": "SUI", "exchange": "binance", "type": "layer1"},
    {"symbol": "SEI", "exchange": "coinbase", "type": "layer1"},
    {"symbol": "TIA", "exchange": "binance", "type": "layer1"},
    {"symbol": "INJ", "exchange": "coinbase", "type": "defi"},
    {"symbol": "PYTH", "exchange": "binance", "type": "oracle"},
    {"symbol": "JTO", "exchange": "coinbase", "type": "defi"},
    {"symbol": "STRK", "exchange": "binance", "type": "layer2"},
]


async def simulate_listing_event() -> Dict[str, Any]:
    """Generate a simulated listing event"""
    listing = random.choice(SIMULATED_LISTINGS)
    
    # Random initial price based on type
    if listing["type"] == "meme":
        price = random.uniform(0.00001, 0.01)
    elif listing["type"] == "layer1":
        price = random.uniform(0.5, 5.0)
    else:
        price = random.uniform(0.1, 2.0)
    
    return {
        "symbol": listing["symbol"],
        "exchange": listing["exchange"],
        "price": price,
        "type": listing["type"],
        "timestamp": datetime.utcnow()
    }


async def simulate_price_movement(
    entry_price: float, 
    token_type: str
) -> tuple[float, str]:
    """
    Simulate realistic price movement after listing
    
    Returns:
        (exit_price, reason)
    """
    # Success rates vary by token type
    success_rates = {
        "meme": 0.40,   # 40% chance of profit (high risk)
        "defi": 0.55,   # 55% chance
        "layer1": 0.60, # 60% chance
        "layer2": 0.55,
        "oracle": 0.50,
    }
    
    success_rate = success_rates.get(token_type, 0.50)
    is_success = random.random() < success_rate
    
    if is_success:
        # Profit scenario
        if token_type == "meme":
            # Meme coins can pump hard
            multiplier = random.uniform(1.3, 5.0)
        else:
            multiplier = random.uniform(1.1, 2.0)
        
        exit_price = entry_price * multiplier
        reason = "Take Profit"
    else:
        # Loss scenario
        multiplier = random.uniform(0.5, 0.9)
        exit_price = entry_price * multiplier
        reason = "Stop Loss"
    
    return exit_price, reason


async def run_training_cycle(paper_trader):
    """Run one training cycle (buy -> wait -> sell)"""
    # Generate listing event
    listing = await simulate_listing_event()
    
    symbol = f"{listing['symbol']}/USDT"
    entry_price = listing["price"]
    
    logger.info(f"[TRAIN] Simulated listing: {listing['symbol']} @ ${entry_price:.6f} on {listing['exchange']}")
    
    # Execute buy
    position = await paper_trader.buy(
        symbol=symbol,
        price=entry_price,
        reason=f"Training - {listing['exchange']} listing"
    )
    
    if not position:
        return None
    
    # Simulate holding time (1-5 seconds for training speed)
    hold_time = random.uniform(1, 5)
    await asyncio.sleep(hold_time)
    
    # Simulate price movement
    exit_price, reason = await simulate_price_movement(
        entry_price, 
        listing["type"]
    )
    
    # Execute sell
    trade = await paper_trader.sell(
        symbol=symbol,
        price=exit_price,
        reason=f"Training - {reason}"
    )
    
    return trade


async def start_training(
    interval_seconds: int = 60,
    max_concurrent_positions: int = 3
):
    """
    Start the training simulator
    
    Periodically simulates new listings and executes paper trades
    to train the bot and accumulate statistics.
    
    Args:
        interval_seconds: Time between new listing simulations
        max_concurrent_positions: Max number of open positions
    """
    paper_trader = get_paper_trader()
    await paper_trader.initialize()
    
    logger.info("=" * 60)
    logger.info("[TRAIN] TRAINING SIMULATOR STARTED")
    logger.info("=" * 60)
    logger.info(f"[TRAIN] Initial capital: ${paper_trader.portfolio.initial_capital:,.2f}")
    logger.info(f"[TRAIN] Interval: {interval_seconds}s between simulations")
    logger.info("=" * 60)
    
    cycle_count = 0
    
    while True:
        try:
            # Check if we can open more positions
            open_positions = len(paper_trader.portfolio.positions)
            
            if open_positions < max_concurrent_positions:
                cycle_count += 1
                logger.info(f"[TRAIN] === Training Cycle #{cycle_count} ===")
                
                # Run training cycle
                trade = await run_training_cycle(paper_trader)
                
                if trade:
                    # Print portfolio status
                    paper_trader.print_status()
            
            # Wait before next cycle
            await asyncio.sleep(interval_seconds)
            
        except asyncio.CancelledError:
            logger.info("[TRAIN] Training simulator stopped")
            break
        except Exception as e:
            logger.error(f"[TRAIN] Training error: {e}")
            await asyncio.sleep(10)


async def run_quick_training(num_cycles: int = 10):
    """
    Run quick training session with specified number of cycles
    
    For testing purposes - runs fast without waiting.
    """
    paper_trader = get_paper_trader()
    await paper_trader.initialize()
    
    logger.info(f"[TRAIN] Starting quick training: {num_cycles} cycles")
    
    for i in range(num_cycles):
        logger.info(f"[TRAIN] Cycle {i+1}/{num_cycles}")
        await run_training_cycle(paper_trader)
        await asyncio.sleep(0.5)  # Small delay between cycles
    
    logger.info("[TRAIN] Quick training complete!")
    paper_trader.print_status()
    
    return paper_trader.get_stats()
