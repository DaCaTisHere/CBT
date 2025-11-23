"""
Tests for Risk Manager
"""

import pytest
from decimal import Decimal
from src.core.risk_manager import RiskManager


@pytest.fixture
def risk_manager():
    """Create risk manager instance"""
    rm = RiskManager()
    return rm


@pytest.mark.asyncio
async def test_risk_manager_initialization(risk_manager):
    """Test risk manager initializes correctly"""
    await risk_manager.initialize()
    assert risk_manager.current_capital > 0
    assert risk_manager.trading_enabled is True


@pytest.mark.asyncio
async def test_position_size_limit(risk_manager):
    """Test position size limits are enforced"""
    await risk_manager.initialize()
    
    # Test within limit
    can_trade, reason = await risk_manager.check_can_trade("test", Decimal("500"))
    assert can_trade is True
    
    # Test exceeding limit
    can_trade, reason = await risk_manager.check_can_trade("test", Decimal("50000"))
    assert can_trade is False
    assert "exceeds limit" in reason


@pytest.mark.asyncio
async def test_daily_loss_limit(risk_manager):
    """Test daily loss limit protection"""
    await risk_manager.initialize()
    
    # Simulate large loss
    risk_manager.current_capital = risk_manager.daily_start_capital * Decimal("0.94")  # -6%
    
    await risk_manager.check_global_limits()
    
    assert risk_manager.daily_loss_exceeded is True
    assert risk_manager.trading_enabled is False


def test_stop_loss_calculation(risk_manager):
    """Test stop-loss price calculation"""
    entry_price = Decimal("100")
    
    # Long position
    sl_long = risk_manager._calculate_stop_loss(entry_price, "LONG")
    assert sl_long < entry_price
    
    # Short position
    sl_short = risk_manager._calculate_stop_loss(entry_price, "SHORT")
    assert sl_short > entry_price

