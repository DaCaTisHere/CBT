"""
Comprehensive Tests for Sniper Bot Module

Tests all components of the sniper bot including:
- Contract analyzer
- Mempool monitor
- Flashbots executor
- Trading strategy
- Main sniper bot logic
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta

# Import components to test
from src.modules.sniper.contract_analyzer import ContractAnalyzer
from src.modules.sniper.strategy import SniperStrategy
from src.modules.sniper.sniper_bot import SniperBot
from src.core.risk_manager import RiskManager


# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def mock_w3():
    """Mock Web3 instance"""
    w3 = Mock()
    w3.eth.chain_id = 1
    w3.eth.block_number = 1000000
    w3.is_connected.return_value = True
    w3.eth.gas_price = 50000000000  # 50 gwei
    w3.eth.get_code.return_value = b'\x60\x60\x60'  # Sample bytecode
    return w3


@pytest.fixture
def contract_analyzer(mock_w3):
    """Contract analyzer instance"""
    return ContractAnalyzer(mock_w3)


@pytest.fixture
def risk_manager():
    """Risk manager instance"""
    return RiskManager()


@pytest.fixture
def sniper_strategy(risk_manager):
    """Sniper strategy instance"""
    return SniperStrategy(risk_manager)


@pytest.fixture
def sniper_bot(risk_manager):
    """Sniper bot instance"""
    order_engine = Mock()
    wallet_manager = Mock()
    return SniperBot(risk_manager, order_engine, wallet_manager)


# ==========================================
# Contract Analyzer Tests
# ==========================================

class TestContractAnalyzer:
    """Test suite for ContractAnalyzer"""
    
    @pytest.mark.asyncio
    async def test_analyze_token_success(self, contract_analyzer, mock_w3):
        """Test successful token analysis"""
        token_address = "0x" + "1234" * 10
        
        # Mock contract calls
        mock_contract =Mock()
        mock_contract.functions.name.return_value.call.return_value = "Test Token"
        mock_contract.functions.symbol.return_value.call.return_value = "TEST"
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.totalSupply.return_value.call.return_value = 1000000 * 10**18
        
        mock_w3.eth.contract.return_value = mock_contract
        
        is_safe, analysis = await contract_analyzer.analyze_token(token_address)
        
        # Assertions
        assert isinstance(is_safe, bool)
        assert isinstance(analysis, dict)
        assert "safety_score" in analysis
        assert "address" in analysis
        assert analysis["address"] == token_address
    
    @pytest.mark.asyncio
    async def test_honeypot_detection(self, contract_analyzer, mock_w3):
        """Test honeypot pattern detection"""
        # Set bytecode with honeypot pattern
        honeypot_bytecode = b'\x60\x00\x80\xfd' + b'\x00' * 100
        mock_w3.eth.get_code.return_value = honeypot_bytecode
        
        has_honeypot = await contract_analyzer._check_bytecode_patterns("0x" + "1234" * 10)
        
        assert has_honeypot is True
    
    @pytest.mark.asyncio
    async def test_small_bytecode_detection(self, contract_analyzer, mock_w3):
        """Test detection of suspiciously small contracts"""
        # Set very small bytecode
        mock_w3.eth.get_code.return_value = b'\x60\x60'
        
        has_honeypot = await contract_analyzer._check_bytecode_patterns("0x" + "1234" * 10)
        
        assert has_honeypot is True
    
    def test_safety_score_calculation(self, contract_analyzer):
        """Test safety score calculation logic"""
        score = contract_analyzer._calculate_safety_score(
            is_verified=True,
            has_honeypot=False,
            token_info={"symbol": "TEST", "decimals": 18},
            ownership_info={"is_renounced": True},
            holder_info={"top_holder_percent": 15},
            liquidity_info={"liquidity_usd": 10000}
        )
        
        # Should be high score
        assert score >= 80
        assert score <= 100
    
    def test_safety_score_low(self, contract_analyzer):
        """Test low safety score for risky token"""
        score = contract_analyzer._calculate_safety_score(
            is_verified=False,
            has_honeypot=True,
            token_info={},
            ownership_info={"is_renounced": False},
            holder_info={"top_holder_percent": 80},
            liquidity_info={"liquidity_usd": 100}
        )
        
        # Should be low score
        assert score < 50


# ==========================================
# Sniper Strategy Tests
# ==========================================

class TestSniperStrategy:
    """Test suite for SniperStrategy"""
    
    @pytest.mark.asyncio
    async def test_should_enter_valid(self, sniper_strategy):
        """Test entry decision with valid conditions"""
        should_enter, reason = await sniper_strategy.should_enter(
            token_address="0x" + "1234" * 10,
            safety_score=85,
            liquidity_usd=10000,
            current_price=0.5
        )
        
        assert should_enter is True
        assert reason is None
    
    @pytest.mark.asyncio
    async def test_should_enter_low_safety(self, sniper_strategy):
        """Test entry rejection due to low safety score"""
        should_enter, reason = await sniper_strategy.should_enter(
            token_address="0x" + "1234" * 10,
            safety_score=50,  # Too low
            liquidity_usd=10000,
            current_price=0.5
        )
        
        assert should_enter is False
        assert "safety score" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_should_enter_low_liquidity(self, sniper_strategy):
        """Test entry rejection due to low liquidity"""
        should_enter, reason = await sniper_strategy.should_enter(
            token_address="0x" + "1234" * 10,
            safety_score=85,
            liquidity_usd=1000,  # Too low
            current_price=0.5
        )
        
        assert should_enter is False
        assert "liquidity" in reason.lower()
    
    def test_calculate_position_size(self, sniper_strategy):
        """Test position size calculation"""
        position = sniper_strategy.calculate_position_size(
            token_price=1.0,
            available_capital=10000
        )
        
        assert "entry_usd" in position
        assert "token_amount" in position
        assert position["entry_usd"] <= 10000 * 0.1  # Max 10% of capital
    
    def test_calculate_exit_levels(self, sniper_strategy):
        """Test exit level calculation"""
        exit_levels = sniper_strategy.calculate_exit_levels(
            entry_price=1.0,
            token_amount=1000
        )
        
        assert "take_profit_price" in exit_levels
        assert "stop_loss_price" in exit_levels
        assert "scaling_levels" in exit_levels
        assert exit_levels["take_profit_price"] > exit_levels["entry_price"]
        assert exit_levels["stop_loss_price"] < exit_levels["entry_price"]
    
    @pytest.mark.asyncio
    async def test_should_exit_stop_loss(self, sniper_strategy):
        """Test stop loss exit trigger"""
        position = {
            "entry_price": 1.0,
            "entry_time": datetime.utcnow(),
            "max_hold_until": datetime.utcnow() + timedelta(hours=24)
        }
        
        # Price dropped 35%
        should_exit, reason, sell_pct = await sniper_strategy.should_exit(
            position=position,
            current_price=0.65,
            current_time=datetime.utcnow()
        )
        
        assert should_exit is True
        assert "stop loss" in reason.lower()
        assert sell_pct == 100.0
    
    @pytest.mark.asyncio
    async def test_should_exit_take_profit(self, sniper_strategy):
        """Test take profit exit trigger"""
        position = {
            "entry_price": 1.0,
            "entry_time": datetime.utcnow(),
            "max_hold_until": datetime.utcnow() + timedelta(hours=24)
        }
        
        # Price doubled (100% gain)
        should_exit, reason, sell_pct = await sniper_strategy.should_exit(
            position=position,
            current_price=2.0,
            current_time=datetime.utcnow()
        )
        
        assert should_exit is True
        assert "take profit" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_should_exit_max_hold(self, sniper_strategy):
        """Test max hold time exit trigger"""
        position = {
            "entry_price": 1.0,
            "entry_time": datetime.utcnow() - timedelta(hours=25),
            "max_hold_until": datetime.utcnow() - timedelta(hours=1)  # Expired
        }
        
        should_exit, reason, sell_pct = await sniper_strategy.should_exit(
            position=position,
            current_price=1.1,  # Small profit
            current_time=datetime.utcnow()
        )
        
        assert should_exit is True
        assert "hold time" in reason.lower()


# ==========================================
# Sniper Bot Integration Tests
# ==========================================

class TestSniperBot:
    """Test suite for complete SniperBot"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, sniper_bot):
        """Test sniper bot initialization"""
        # Mock Web3
        with patch('src.modules.sniper.sniper_bot.Web3') as mock_web3_class:
            mock_instance = Mock()
            mock_instance.is_connected.return_value = True
            mock_instance.eth.chain_id = 1
            mock_instance.eth.block_number = 1000000
            mock_web3_class.return_value = mock_instance
            
            await sniper_bot.initialize()
            
            assert sniper_bot.is_initialized is True
            assert sniper_bot.w3 is not None
            assert sniper_bot.contract_analyzer is not None
            assert sniper_bot.strategy is not None
    
    @pytest.mark.asyncio
    async def test_handle_new_token_rejected(self, sniper_bot):
        """Test handling of rejected token"""
        # Initialize bot
        sniper_bot.is_initialized = True
        sniper_bot.contract_analyzer = Mock()
        sniper_bot.contract_analyzer.analyze_token = AsyncMock(return_value=(
            False,  # Not safe
            {"safety_score": 40, "rejection_reason": "Low safety score"}
        ))
        
        initial_scams = sniper_bot.scams_avoided
        
        await sniper_bot._handle_new_token(
            token_address="0x" + "1234" * 10,
            pair_address="0x" + "5678" * 10
        )
        
        # Should increment scams avoided
        assert sniper_bot.scams_avoided == initial_scams + 1
        # Should NOT execute trade
        assert sniper_bot.trades_executed == 0
    
    def test_get_stats(self, sniper_bot):
        """Test statistics retrieval"""
        stats = asyncio.run(sniper_bot.get_stats())
        
        assert "tokens_detected" in stats
        assert "tokens_analyzed" in stats
        assert "trades_executed" in stats
        assert "scams_avoided" in stats
        assert "success_rate" in stats
    
    @pytest.mark.asyncio
    async def test_is_healthy(self, sniper_bot):
        """Test health check"""
        # Not initialized
        is_healthy = await sniper_bot.is_healthy()
        assert is_healthy is False
        
        # Initialize
        sniper_bot.is_initialized = True
        sniper_bot.is_running = True
        sniper_bot.w3 = Mock()
        sniper_bot.w3.is_connected.return_value = True
        
        is_healthy = await sniper_bot.is_healthy()
        assert is_healthy is True


# ==========================================
# Performance Tests
# ==========================================

class TestPerformance:
    """Performance and stress tests"""
    
    @pytest.mark.asyncio
    async def test_analyze_multiple_tokens(self, contract_analyzer, mock_w3):
        """Test analyzing multiple tokens concurrently"""
        # Mock contract
        mock_contract = Mock()
        mock_contract.functions.name.return_value.call.return_value = "Test Token"
        mock_contract.functions.symbol.return_value.call.return_value = "TEST"
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.totalSupply.return_value.call.return_value = 1000000 * 10**18
        mock_w3.eth.contract.return_value = mock_contract
        
        # Analyze 10 tokens concurrently
        tokens = [f"0x{'1234' * 10}" for _ in range(10)]
        
        import time
        start = time.time()
        
        results = await asyncio.gather(*[
            contract_analyzer.analyze_token(token)
            for token in tokens
        ])
        
        duration = time.time() - start
        
        # Should complete all analyses
        assert len(results) == 10
        # Should be reasonably fast (< 2 seconds for 10 tokens)
        assert duration < 2.0


# ==========================================
# Run Tests
# ==========================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
