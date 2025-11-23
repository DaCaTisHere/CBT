"""
Helper functions and utilities
"""

from decimal import Decimal
from typing import Union


def format_price(price: Union[float, Decimal], decimals: int = 2) -> str:
    """
    Format price with proper decimals
    
    Args:
        price: Price value
        decimals: Number of decimal places
    
    Returns:
        Formatted price string
    """
    return f"${price:,.{decimals}f}"


def format_percentage(value: Union[float, Decimal], decimals: int = 2) -> str:
    """
    Format percentage value
    
    Args:
        value: Percentage value
        decimals: Number of decimal places
    
    Returns:
        Formatted percentage string
    """
    return f"{value:.{decimals}f}%"


def calculate_pnl(entry_price: Decimal, exit_price: Decimal, 
                  amount: Decimal, side: str = "LONG") -> Decimal:
    """
    Calculate profit/loss for a trade
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        amount: Position size in USD
        side: LONG or SHORT
    
    Returns:
        PnL in USD
    """
    if side == "LONG":
        price_change = (exit_price - entry_price) / entry_price
    else:  # SHORT
        price_change = (entry_price - exit_price) / entry_price
    
    return amount * price_change


def wei_to_eth(wei: int) -> Decimal:
    """Convert Wei to ETH"""
    return Decimal(wei) / Decimal(10**18)


def eth_to_wei(eth: Union[float, Decimal]) -> int:
    """Convert ETH to Wei"""
    return int(Decimal(eth) * Decimal(10**18))


def truncate_address(address: str, chars: int = 6) -> str:
    """
    Truncate blockchain address for display
    
    Args:
        address: Full address
        chars: Number of chars to keep on each end
    
    Returns:
        Truncated address like 0x1234...5678
    """
    if len(address) <= chars * 2:
        return address
    return f"{address[:chars]}...{address[-chars:]}"

