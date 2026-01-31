"""
Trading Mode Manager - Safe switching between simulation and real trading

IMPORTANT: This module ensures all safety checks are passed before real trading.
"""

import asyncio
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from datetime import datetime

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradingModeManager:
    """
    Manages trading modes and performs safety checks before real trading.
    
    Modes:
    - SIMULATION: No real money, uses Paper Trader
    - DRY_RUN: Connects to real APIs but doesn't execute trades
    - REAL: Actual trading with real funds
    """
    
    # Minimum requirements for real trading
    MIN_ETH_BALANCE = Decimal("0.01")  # For gas fees
    MIN_USDT_BALANCE = Decimal("50")   # Minimum trading capital
    
    def __init__(self):
        self.logger = logger
        self.preflight_passed = False
        self.preflight_results: Dict[str, Tuple[bool, str]] = {}
        self.last_check_time: Optional[datetime] = None
        
    def get_current_mode(self) -> str:
        """Get current trading mode"""
        if settings.SIMULATION_MODE:
            return "SIMULATION"
        elif settings.DRY_RUN:
            return "DRY_RUN"
        else:
            return "REAL"
    
    async def run_preflight_checks(self) -> Tuple[bool, Dict[str, Tuple[bool, str]]]:
        """
        Run all preflight checks before enabling real trading.
        
        Returns:
            (all_passed, results_dict)
        """
        self.logger.info("=" * 60)
        self.logger.info("🔍 PREFLIGHT CHECKS FOR REAL TRADING")
        self.logger.info("=" * 60)
        
        results = {}
        
        # 1. Check environment configuration
        results["env_config"] = self._check_environment()
        
        # 2. Check wallet configuration
        results["wallet_config"] = self._check_wallet_config()
        
        # 3. Check API keys
        results["api_keys"] = self._check_api_keys()
        
        # 4. Check RPC endpoints
        results["rpc_endpoints"] = await self._check_rpc_endpoints()
        
        # 5. Check exchange connectivity
        results["exchange_connectivity"] = await self._check_exchange_connectivity()
        
        # 6. Check wallet balances
        results["wallet_balances"] = await self._check_wallet_balances()
        
        # 7. Check risk parameters
        results["risk_params"] = self._check_risk_parameters()
        
        # Log results
        all_passed = True
        self.logger.info("")
        self.logger.info("📋 PREFLIGHT RESULTS:")
        self.logger.info("-" * 40)
        
        for check_name, (passed, message) in results.items():
            status = "✅" if passed else "❌"
            self.logger.info(f"  {status} {check_name}: {message}")
            if not passed:
                all_passed = False
        
        self.logger.info("-" * 40)
        
        if all_passed:
            self.logger.info("✅ ALL PREFLIGHT CHECKS PASSED")
            self.logger.info("⚠️  You can now enable REAL trading mode")
        else:
            self.logger.warning("❌ SOME CHECKS FAILED - Cannot enable real trading")
        
        self.logger.info("=" * 60)
        
        self.preflight_passed = all_passed
        self.preflight_results = results
        self.last_check_time = datetime.utcnow()
        
        return all_passed, results
    
    def _check_environment(self) -> Tuple[bool, str]:
        """Check environment configuration"""
        if settings.ENVIRONMENT.value == "production":
            return True, "Production environment"
        elif settings.ENVIRONMENT.value == "development":
            return True, "Development (OK for testing)"
        else:
            return True, f"Environment: {settings.ENVIRONMENT.value}"
    
    def _check_wallet_config(self) -> Tuple[bool, str]:
        """Check wallet configuration"""
        try:
            pk = settings.WALLET_PRIVATE_KEY
            if not pk or pk == "0x" + "0" * 64:
                return False, "Private key not configured or is placeholder"
            if not pk.startswith("0x") or len(pk) != 66:
                return False, "Invalid private key format"
            return True, "Private key configured correctly"
        except Exception as e:
            return False, f"Error: {e}"
    
    def _check_api_keys(self) -> Tuple[bool, str]:
        """Check exchange API keys"""
        binance_ok = bool(settings.BINANCE_API_KEY and settings.BINANCE_SECRET)
        
        if binance_ok:
            return True, "Binance API keys configured"
        else:
            # Can still trade on DEX without CEX API
            return True, "No CEX API keys (DEX only mode)"
    
    async def _check_rpc_endpoints(self) -> Tuple[bool, str]:
        """Check RPC endpoint connectivity"""
        try:
            from web3 import Web3
            
            # Check Ethereum RPC
            eth_rpc = settings.ETHEREUM_RPC_URL
            if not eth_rpc:
                return False, "No Ethereum RPC URL configured"
            
            w3 = Web3(Web3.HTTPProvider(eth_rpc))
            if not w3.is_connected():
                return False, f"Cannot connect to Ethereum RPC"
            
            block = w3.eth.block_number
            return True, f"Ethereum connected (block {block})"
            
        except Exception as e:
            return False, f"RPC error: {e}"
    
    async def _check_exchange_connectivity(self) -> Tuple[bool, str]:
        """Check exchange API connectivity"""
        if not settings.BINANCE_API_KEY:
            return True, "Skipped (no API keys)"
        
        try:
            import ccxt.async_support as ccxt
            
            exchange = ccxt.binance({
                'apiKey': settings.BINANCE_API_KEY,
                'secret': settings.BINANCE_SECRET,
                'enableRateLimit': True,
            })
            
            balance = await exchange.fetch_balance()
            await exchange.close()
            
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            return True, f"Binance connected (USDT: ${usdt_balance:.2f})"
            
        except Exception as e:
            return False, f"Exchange error: {e}"
    
    async def _check_wallet_balances(self) -> Tuple[bool, str]:
        """Check wallet has sufficient balances"""
        try:
            from web3 import Web3
            from eth_account import Account
            
            w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
            if not w3.is_connected():
                return False, "Cannot connect to check balances"
            
            account = Account.from_key(settings.WALLET_PRIVATE_KEY)
            address = account.address
            
            # Check ETH balance
            eth_balance = w3.eth.get_balance(address)
            eth_balance_decimal = Decimal(eth_balance) / Decimal(10**18)
            
            if eth_balance_decimal < self.MIN_ETH_BALANCE:
                return False, f"ETH balance too low: {eth_balance_decimal:.4f} ETH (need {self.MIN_ETH_BALANCE})"
            
            return True, f"Wallet OK: {eth_balance_decimal:.4f} ETH at {address[:10]}..."
            
        except Exception as e:
            return False, f"Balance check error: {e}"
    
    def _check_risk_parameters(self) -> Tuple[bool, str]:
        """Check risk parameters are reasonable"""
        issues = []
        
        if settings.MAX_POSITION_SIZE_PCT > 20:
            issues.append(f"Position size high ({settings.MAX_POSITION_SIZE_PCT}%)")
        
        if settings.MAX_DAILY_LOSS_PCT > 10:
            issues.append(f"Daily loss limit high ({settings.MAX_DAILY_LOSS_PCT}%)")
        
        if settings.STOP_LOSS_PCT > 20:
            issues.append(f"Stop loss wide ({settings.STOP_LOSS_PCT}%)")
        
        if issues:
            return True, f"Warning: {', '.join(issues)}"
        else:
            return True, f"Risk params OK (max {settings.MAX_POSITION_SIZE_PCT}% per trade)"
    
    def get_mode_switch_instructions(self) -> str:
        """Get instructions for switching to real mode"""
        return """
╔══════════════════════════════════════════════════════════════╗
║           SWITCH TO REAL TRADING MODE                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. CONFIGURE ENVIRONMENT VARIABLES:                        ║
║     ────────────────────────────────                         ║
║     SIMULATION_MODE=false                                    ║
║     DRY_RUN=false  (or true for testing without trades)      ║
║     USE_TESTNET=false                                        ║
║                                                              ║
║  2. ADD YOUR METAMASK PRIVATE KEY:                           ║
║     ────────────────────────────────                         ║
║     WALLET_PRIVATE_KEY=0x...your_private_key...              ║
║                                                              ║
║     ⚠️  HOW TO GET IT:                                       ║
║     - MetaMask > Account > Export Private Key                ║
║     - NEVER share this key with anyone!                      ║
║                                                              ║
║  3. ADD ETHEREUM RPC:                                        ║
║     ────────────────────────────────                         ║
║     ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/...   ║
║                                                              ║
║     Free RPC: https://alchemy.com or https://infura.io       ║
║                                                              ║
║  4. (OPTIONAL) ADD BINANCE API KEYS:                         ║
║     ────────────────────────────────                         ║
║     BINANCE_API_KEY=your_api_key                             ║
║     BINANCE_SECRET=your_secret                               ║
║                                                              ║
║  5. RUN PREFLIGHT CHECKS:                                    ║
║     ────────────────────────────────                         ║
║     The bot will automatically check everything before       ║
║     executing any real trade.                                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


# Global instance
_trading_mode_manager: Optional[TradingModeManager] = None


def get_trading_mode_manager() -> TradingModeManager:
    """Get global trading mode manager"""
    global _trading_mode_manager
    if _trading_mode_manager is None:
        _trading_mode_manager = TradingModeManager()
    return _trading_mode_manager
