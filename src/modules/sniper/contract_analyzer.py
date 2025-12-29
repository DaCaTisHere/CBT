"""
Smart Contract Analyzer for Sniper Bot

Analyzes token contracts for safety and honeypot detection.
Provides a safety score (0-100) and detailed analysis.
"""

import asyncio
from typing import Dict, Any, Tuple, Optional
from decimal import Decimal
from web3 import Web3
from web3.contract import Contract
from eth_utils import to_checksum_address

from src.utils.logger import get_logger


logger = get_logger(__name__)


class ContractAnalyzer:
    """
    Analyzes smart contracts for safety and scam detection
    """
    
    # Honeypot indicators in bytecode
    HONEYPOT_PATTERNS = [
        b'\x60\x00\x80\xfd',  # PUSH1 0x00 DUP1 REVERT (instant revert)
        b'\x60\x01\x60\x00\xfd',  # Common honeypot pattern
    ]
    
    # Minimum liquidity in USD to consider safe
    MIN_LIQUIDITY_USD = 5000
    
    # Maximum buy/sell tax percentage
    MAX_TAX_PERCENT = 15
    
    def __init__(self, w3: Web3):
        """
        Initialize contract analyzer
        
        Args:
            w3: Web3 instance
        """
        self.w3 = w3
        self.logger = logger
        
        # ERC20 ABI (minimal for our needs)
        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
        ]
    
    async def analyze_token(self, token_address: str, pair_address: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Comprehensive token safety analysis
        
        Args:
            token_address: Token contract address
            pair_address: Optional pair address for liquidity checks
        
        Returns:
            Tuple of (is_safe: bool, analysis: dict)
        """
        try:
            address = to_checksum_address(token_address)
            
            self.logger.info(f"🔍 Analyzing token: {address[:10]}...")
            
            # Run all checks in parallel for speed
            results = await asyncio.gather(
                self._check_contract_verified(address),
                self._check_bytecode_patterns(address),
                self._check_token_info(address),
                self._check_ownership(address),
                self._check_holder_distribution(address),
                self._check_liquidity(pair_address) if pair_address else asyncio.sleep(0),
                return_exceptions=True
            )
            
            # Unpack results
            is_verified = results[0] if not isinstance(results[0], Exception) else False
            has_honeypot = results[1] if not isinstance(results[1], Exception) else True
            token_info = results[2] if not isinstance(results[2], Exception) else {}
            ownership_info = results[3] if not isinstance(results[3], Exception) else {}
            holder_info = results[4] if not isinstance(results[4], Exception) else {}
            liquidity_info = results[5] if not isinstance(results[5], Exception) else {}
            
            # Calculate safety score (0-100)
            safety_score = self._calculate_safety_score(
                is_verified=is_verified,
                has_honeypot=has_honeypot,
                token_info=token_info,
                ownership_info=ownership_info,
                holder_info=holder_info,
                liquidity_info=liquidity_info
            )
            
            # Compile analysis report
            analysis = {
                "address": address,
                "safety_score": safety_score,
                "is_verified": is_verified,
                "is_honeypot": has_honeypot,
                "token_info": token_info,
                "ownership": ownership_info,
                "holders": holder_info,
                "liquidity": liquidity_info,
                "timestamp": asyncio.get_event_loop().time(),
            }
            
            # Determine if safe to trade
            is_safe = safety_score >= 70 and not has_honeypot
            
            if is_safe:
                self.logger.info(f"   ✅ Token passed safety check (score: {safety_score})")
            else:
                reason = "honeypot detected" if has_honeypot else f"low safety score ({safety_score})"
                self.logger.warning(f"   ❌ Token failed: {reason}")
                analysis["rejection_reason"] = reason
            
            return is_safe, analysis
            
        except Exception as e:
            self.logger.error(f"Token analysis failed: {e}")
            return False, {
                "address": token_address,
                "error": str(e),
                "safety_score": 0,
                "rejection_reason": f"Analysis error: {e}"
            }
    
    async def _check_contract_verified(self, address: str) -> bool:
        """
        Check if contract is verified on Etherscan
        
        In production, this would use Etherscan API.
        For now, we'll return True for demo purposes.
        """
        # TODO: Implement Etherscan API check
        # api_url = f"https://api.etherscan.io/api?module=contract&action=getsourcecode&address={address}"
        
        await asyncio.sleep(0.1)  # Simulate API call
        return True  # Placeholder
    
    async def _check_bytecode_patterns(self, address: str) -> bool:
        """
        Check bytecode for known honeypot patterns
        
        Returns:
            True if honeypot detected, False otherwise
        """
        try:
            bytecode = self.w3.eth.get_code(address)
            
            # Check for honeypot patterns
            for pattern in self.HONEYPOT_PATTERNS:
                if pattern in bytecode:
                    self.logger.warning(f"   ⚠️  Honeypot pattern detected in bytecode")
                    return True
            
            # Check if contract is too small (likely a scam)
            if len(bytecode) < 100:
                self.logger.warning(f"   ⚠️  Contract bytecode too small")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Bytecode check failed: {e}")
            return True  # Assume unsafe on error
    
    async def _check_token_info(self, address: str) -> Dict[str, Any]:
        """
        Get basic token information (name, symbol, decimals, supply)
        """
        try:
            contract = self.w3.eth.contract(address=address, abi=self.erc20_abi)
            
            # Get token info
            name = contract.functions.name().call()
            symbol = contract.functions.symbol().call()
            decimals = contract.functions.decimals().call()
            total_supply = contract.functions.totalSupply().call()
            
            return {
                "name": name,
                "symbol": symbol,
                "decimals": decimals,
                "total_supply": total_supply,
                "supply_formatted": total_supply / (10 ** decimals)
            }
            
        except Exception as e:
            self.logger.error(f"Token info check failed: {e}")
            return {}
    
    async def _check_ownership(self, address: str) -> Dict[str, Any]:
        """
        Check contract ownership and if it's renounced
        
        In production, this would check:
        - If ownership is renounced (owner = 0x0)
        - If contract has minting functions
        - If contract has pause functions
        """
        # TODO: Implement ownership checks
        await asyncio.sleep(0.1)
        
        return {
            "is_renounced": False,  # Placeholder
            "owner": "0x0000000000000000000000000000000000000000",
            "has_mint_function": False,
            "has_pause_function": False,
        }
    
    async def _check_holder_distribution(self, address: str) -> Dict[str, Any]:
        """
        Check token holder distribution
        
        Red flags:
        - Single holder owns >50% of supply
        - Top 10 holders own >90% of supply
        """
        # TODO: Implement holder distribution check
        # This requires indexed data or external API
        
        await asyncio.sleep(0.1)
        
        return {
            "top_holder_percent": 0.0,  # Placeholder
            "top_10_percent": 0.0,
            "holder_count": 0,
        }
    
    async def _check_liquidity(self, pair_address: str) -> Dict[str, Any]:
        """
        Check liquidity pool information
        
        Important metrics:
        - Total liquidity in USD
        - Liquidity locked?
        - Liquidity lock duration
        """
        if not pair_address:
            return {}
        
        # TODO: Implement liquidity checks
        # - Get pair reserves
        # - Calculate liquidity in USD
        # - Check if liquidity is locked (using Unicrypt/Team Finance APIs)
        
        await asyncio.sleep(0.1)
        
        return {
            "liquidity_usd": 0.0,  # Placeholder
            "is_locked": False,
            "lock_duration_days": 0,
        }
    
    def _calculate_safety_score(
        self,
        is_verified: bool,
        has_honeypot: bool,
        token_info: Dict,
        ownership_info: Dict,
        holder_info: Dict,
        liquidity_info: Dict
    ) -> int:
        """
        Calculate overall safety score (0-100)
        
        Scoring breakdown:
        - Contract verified: +20 points
        - No honeypot patterns: +30 points
        - Valid token info: +10 points
        - Ownership renounced: +15 points
        - Good holder distribution: +10 points
        - Sufficient liquidity: +15 points
        """
        score = 0
        
        # Contract verified
        if is_verified:
            score += 20
        
        # No honeypot
        if not has_honeypot:
            score += 30
        
        # Valid token info
        if token_info and "symbol" in token_info and "decimals" in token_info:
            score += 10
        
        # Ownership renounced
        if ownership_info.get("is_renounced", False):
            score += 15
        elif not ownership_info.get("has_mint_function", True):
            score += 10  # No mint function is good
        
        # Holder distribution
        top_holder = holder_info.get("top_holder_percent", 0)
        if top_holder < 20:
            score += 10
        elif top_holder < 50:
            score += 5
        
        # Liquidity
        liquidity_usd = liquidity_info.get("liquidity_usd", 0)
        if liquidity_usd >= self.MIN_LIQUIDITY_USD:
            score += 15
        elif liquidity_usd >= self.MIN_LIQUIDITY_USD / 2:
            score += 8
        
        return min(100, max(0, score))
    
    async def simulate_buy_sell(self, token_address: str, pair_address: str) -> Dict[str, Any]:
        """
        Simulate buy and sell to detect hidden taxes or honeypots
        
        This is the most reliable honeypot detection method but requires
        actually attempting trades.
        
        Returns:
            Dict with buy_tax, sell_tax, and can_sell flag
        """
        # TODO: Implement buy/sell simulation
        # This would:
        # 1. Use eth_call to simulate a buy transaction
        # 2. Calculate expected output
        # 3. Use eth_call to simulate a sell transaction
        # 4. Calculate taxes from slippage
        
        await asyncio.sleep(0.1)
        
        return {
            "can_buy": True,
            "can_sell": True,
            "buy_tax_percent": 0.0,
            "sell_tax_percent": 0.0,
            "total_tax_percent": 0.0,
        }
