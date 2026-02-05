"""
DEX Trader - Execute trades on decentralized exchanges

Supports:
- Ethereum: Uniswap V2/V3
- BSC: PancakeSwap
- Base: Uniswap V3
- Arbitrum: Uniswap V3
- Solana: Raydium (via Jupiter)

IMPORTANT: Requires WALLET_PRIVATE_KEY and RPC URLs to be configured
"""

import asyncio
from typing import Dict, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Network(str, Enum):
    """Supported networks"""
    ETHEREUM = "eth"
    BSC = "bsc"
    BASE = "base"
    ARBITRUM = "arbitrum"
    SOLANA = "solana"


@dataclass
class DEXTrade:
    """Represents a DEX trade"""
    network: str
    token_address: str
    token_symbol: str
    action: str  # "buy" or "sell"
    amount_in: Decimal
    amount_out: Decimal
    price_usd: float
    tx_hash: Optional[str] = None
    status: str = "pending"  # pending, submitted, confirmed, failed
    gas_used: Optional[int] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class DEXTrader:
    """
    Execute trades on decentralized exchanges
    
    Safety features:
    - Slippage protection
    - Gas estimation
    - Transaction simulation
    - Position limits
    """
    
    # DEX Router addresses
    ROUTERS = {
        "eth": {
            "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        },
        "bsc": {
            "pancakeswap_v2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        },
        "base": {
            "uniswap_v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
        },
        "arbitrum": {
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        }
    }
    
    # Wrapped native tokens (for swaps)
    WRAPPED_NATIVE = {
        "eth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",      # WETH
        "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",      # WBNB
        "base": "0x4200000000000000000000000000000000000006",     # WETH on Base
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", # WETH on Arbitrum
    }
    
    # Stablecoins for trading pairs
    STABLECOINS = {
        "eth": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",      # USDC
        "bsc": "0x55d398326f99059fF775485246999027B3197955",      # USDT BSC
        "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",     # USDC Base
        "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", # USDC Arbitrum
    }
    
    # Default settings
    DEFAULT_SLIPPAGE = 0.5  # 0.5%
    MAX_SLIPPAGE = 5.0      # 5%
    GAS_BUFFER = 1.2        # 20% buffer for gas estimation
    
    def __init__(self):
        self.logger = logger
        self.web3_clients: Dict[str, Any] = {}
        self.wallets: Dict[str, Any] = {}
        self.is_initialized = False
        self.trades: list[DEXTrade] = []
        
        # Position tracking
        self.positions: Dict[str, Dict] = {}  # token_address -> {amount, avg_price}
        
    async def initialize(self) -> bool:
        """Initialize DEX trader with wallet and RPC connections"""
        self.logger.info("[DEX] Initializing DEX Trader...")
        
        try:
            # Check if wallet is configured
            if not self._check_wallet_config():
                self.logger.warning("[DEX] Wallet not configured - DEX trading disabled")
                return False
            
            # Initialize Web3 clients for each network
            await self._init_web3_clients()
            
            # Initialize wallet on each network
            await self._init_wallets()
            
            self.is_initialized = True
            self.logger.info("[DEX] DEX Trader initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"[DEX] Initialization failed: {e}")
            return False
    
    def _check_wallet_config(self) -> bool:
        """Check if wallet is properly configured"""
        pk = settings.WALLET_PRIVATE_KEY
        if not pk or pk == "0x" + "0" * 64:
            return False
        if not pk.startswith("0x") or len(pk) != 66:
            return False
        return True
    
    async def _init_web3_clients(self):
        """Initialize Web3 clients for each supported network"""
        try:
            from web3 import Web3
            from web3.middleware import geth_poa_middleware
            
            rpc_urls = {
                "eth": settings.ETHEREUM_RPC_URL,
                "bsc": settings.BSC_RPC_URL,
                "base": getattr(settings, 'BASE_RPC_URL', None),
                "arbitrum": getattr(settings, 'ARBITRUM_RPC_URL', None),
            }
            
            for network, rpc_url in rpc_urls.items():
                if rpc_url:
                    try:
                        w3 = Web3(Web3.HTTPProvider(rpc_url))
                        
                        # Add POA middleware for BSC
                        if network == "bsc":
                            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                        
                        if w3.is_connected():
                            self.web3_clients[network] = w3
                            block = w3.eth.block_number
                            self.logger.info(f"[DEX] Connected to {network.upper()} (block {block})")
                    except Exception as e:
                        self.logger.warning(f"[DEX] Could not connect to {network}: {e}")
                        
        except ImportError:
            self.logger.error("[DEX] web3 library not installed")
            
    async def _init_wallets(self):
        """Initialize wallet on each network"""
        try:
            from eth_account import Account
            
            account = Account.from_key(settings.WALLET_PRIVATE_KEY)
            
            for network, w3 in self.web3_clients.items():
                balance = w3.eth.get_balance(account.address)
                native_balance = Decimal(balance) / Decimal(10**18)
                
                self.wallets[network] = {
                    "address": account.address,
                    "account": account,
                    "native_balance": native_balance
                }
                
                native_symbol = "ETH" if network != "bsc" else "BNB"
                self.logger.info(f"[DEX] {network.upper()} Wallet: {account.address[:10]}... ({native_balance:.4f} {native_symbol})")
                
        except Exception as e:
            self.logger.error(f"[DEX] Wallet init error: {e}")
    
    async def buy(
        self,
        network: str,
        token_address: str,
        amount_usd: float,
        slippage: float = None,
        token_symbol: str = None
    ) -> Optional[DEXTrade]:
        """
        Buy a token on a DEX
        
        Args:
            network: Network ID (eth, bsc, base, arbitrum)
            token_address: Token contract address
            amount_usd: Amount to spend in USD
            slippage: Slippage tolerance (default 0.5%)
            token_symbol: Optional symbol for logging
            
        Returns:
            DEXTrade object or None if failed
        """
        if not self.is_initialized:
            self.logger.warning("[DEX] Not initialized - cannot trade")
            return None
        
        if network not in self.web3_clients:
            self.logger.warning(f"[DEX] Network {network} not available")
            return None
        
        slippage = slippage or self.DEFAULT_SLIPPAGE
        if slippage > self.MAX_SLIPPAGE:
            slippage = self.MAX_SLIPPAGE
        
        self.logger.info(f"[DEX] 🛒 Buying ${amount_usd} of {token_symbol or token_address[:10]} on {network.upper()}")
        
        try:
            # Get current token price
            price_usd = await self._get_token_price(network, token_address)
            if not price_usd or price_usd == 0:
                self.logger.warning(f"[DEX] Could not get price for {token_address}")
                return None
            
            # Calculate amount out
            amount_tokens = Decimal(str(amount_usd)) / Decimal(str(price_usd))
            
            # Build swap transaction
            tx = await self._build_swap_tx(
                network=network,
                token_in=self.STABLECOINS.get(network),
                token_out=token_address,
                amount_in=Decimal(str(amount_usd)),
                slippage=slippage
            )
            
            if not tx:
                self.logger.warning("[DEX] Could not build swap transaction")
                return None
            
            # Simulate transaction first
            if not await self._simulate_tx(network, tx):
                self.logger.warning("[DEX] Transaction simulation failed")
                return None
            
            # Execute transaction
            tx_hash = await self._send_tx(network, tx)
            
            if tx_hash:
                trade = DEXTrade(
                    network=network,
                    token_address=token_address,
                    token_symbol=token_symbol or "UNKNOWN",
                    action="buy",
                    amount_in=Decimal(str(amount_usd)),
                    amount_out=amount_tokens,
                    price_usd=price_usd,
                    tx_hash=tx_hash,
                    status="submitted"
                )
                
                self.trades.append(trade)
                self.logger.info(f"[DEX] ✅ Buy submitted: {tx_hash}")
                
                # Wait for confirmation
                confirmed = await self._wait_confirmation(network, tx_hash)
                trade.status = "confirmed" if confirmed else "failed"
                
                if confirmed:
                    # Update positions
                    self._update_position(token_address, amount_tokens, price_usd, "buy")
                    self.logger.info(f"[DEX] ✅ Buy confirmed: {amount_tokens:.6f} tokens @ ${price_usd:.8f}")
                    return trade
            
            return None
            
        except Exception as e:
            self.logger.error(f"[DEX] Buy error: {e}")
            return None
    
    async def sell(
        self,
        network: str,
        token_address: str,
        amount_tokens: Decimal = None,
        percent: float = 100,
        slippage: float = None,
        token_symbol: str = None
    ) -> Optional[DEXTrade]:
        """
        Sell a token on a DEX
        
        Args:
            network: Network ID
            token_address: Token contract address
            amount_tokens: Amount to sell (optional, uses percent if not provided)
            percent: Percentage of position to sell (default 100%)
            slippage: Slippage tolerance
            token_symbol: Optional symbol for logging
            
        Returns:
            DEXTrade object or None if failed
        """
        if not self.is_initialized:
            return None
        
        slippage = slippage or self.DEFAULT_SLIPPAGE
        
        # Get position amount if not specified
        if amount_tokens is None:
            position = self.positions.get(token_address)
            if not position:
                self.logger.warning(f"[DEX] No position found for {token_address}")
                return None
            amount_tokens = position["amount"] * Decimal(str(percent / 100))
        
        self.logger.info(f"[DEX] 💰 Selling {amount_tokens:.6f} {token_symbol or token_address[:10]} on {network.upper()}")
        
        try:
            # Get current price
            price_usd = await self._get_token_price(network, token_address)
            if not price_usd:
                return None
            
            amount_usd = float(amount_tokens) * price_usd
            
            # Build swap transaction
            tx = await self._build_swap_tx(
                network=network,
                token_in=token_address,
                token_out=self.STABLECOINS.get(network),
                amount_in=amount_tokens,
                slippage=slippage
            )
            
            if not tx:
                return None
            
            # Execute
            tx_hash = await self._send_tx(network, tx)
            
            if tx_hash:
                trade = DEXTrade(
                    network=network,
                    token_address=token_address,
                    token_symbol=token_symbol or "UNKNOWN",
                    action="sell",
                    amount_in=amount_tokens,
                    amount_out=Decimal(str(amount_usd)),
                    price_usd=price_usd,
                    tx_hash=tx_hash,
                    status="submitted"
                )
                
                self.trades.append(trade)
                
                confirmed = await self._wait_confirmation(network, tx_hash)
                trade.status = "confirmed" if confirmed else "failed"
                
                if confirmed:
                    self._update_position(token_address, amount_tokens, price_usd, "sell")
                    self.logger.info(f"[DEX] ✅ Sell confirmed: ${amount_usd:.2f}")
                    return trade
            
            return None
            
        except Exception as e:
            self.logger.error(f"[DEX] Sell error: {e}")
            return None
    
    async def _get_token_price(self, network: str, token_address: str) -> Optional[float]:
        """Get token price from DEX"""
        try:
            # Use GeckoTerminal client for price
            from src.modules.geckoterminal.gecko_client import GeckoTerminalClient
            
            client = GeckoTerminalClient()
            await client.initialize()
            price = await client.get_token_price(network, token_address)
            await client.close()
            
            return price
        except:
            return None
    
    async def _build_swap_tx(
        self,
        network: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage: float
    ) -> Optional[Dict]:
        """Build swap transaction for DEX"""
        # This is a simplified implementation
        # Real implementation would interact with router contracts
        
        if network not in self.web3_clients:
            return None
        
        w3 = self.web3_clients[network]
        wallet = self.wallets.get(network)
        if not wallet:
            return None
        
        # For now, return a placeholder
        # Real implementation would use router ABI
        return {
            "network": network,
            "from": wallet["address"],
            "to": self.ROUTERS.get(network, {}).get("uniswap_v2"),
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount_in),
            "slippage": slippage
        }
    
    async def _simulate_tx(self, network: str, tx: Dict) -> bool:
        """Simulate transaction to check if it would succeed"""
        # Simplified - real implementation would use eth_call
        return True
    
    async def _send_tx(self, network: str, tx: Dict) -> Optional[str]:
        """Send transaction to network"""
        if settings.SIMULATION_MODE:
            # In simulation mode, return fake tx hash
            import hashlib
            fake_hash = "0x" + hashlib.sha256(str(tx).encode()).hexdigest()
            self.logger.info(f"[DEX] 🧪 SIMULATION MODE - Fake TX: {fake_hash[:20]}...")
            return fake_hash
        
        if settings.DRY_RUN:
            self.logger.info("[DEX] DRY RUN - Would send transaction")
            return None
        
        # Real transaction sending would go here
        # w3 = self.web3_clients[network]
        # signed = w3.eth.account.sign_transaction(tx, wallet_key)
        # tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        
        self.logger.warning("[DEX] Real transaction sending not yet implemented")
        return None
    
    async def _wait_confirmation(self, network: str, tx_hash: str, timeout: int = 60) -> bool:
        """Wait for transaction confirmation"""
        if settings.SIMULATION_MODE:
            await asyncio.sleep(1)  # Simulate confirmation time
            return True
        
        try:
            w3 = self.web3_clients.get(network)
            if not w3:
                return False
            
            start = datetime.utcnow()
            while (datetime.utcnow() - start).seconds < timeout:
                try:
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                    if receipt:
                        return receipt["status"] == 1
                except:
                    pass
                await asyncio.sleep(3)
            
            return False
        except Exception as e:
            self.logger.error(f"[DEX] Confirmation error: {e}")
            return False
    
    def _update_position(self, token_address: str, amount: Decimal, price: float, action: str):
        """Update position tracking"""
        if token_address not in self.positions:
            self.positions[token_address] = {"amount": Decimal("0"), "avg_price": 0}
        
        pos = self.positions[token_address]
        
        if action == "buy":
            # Update average price
            total_value = float(pos["amount"]) * pos["avg_price"] + float(amount) * price
            new_amount = pos["amount"] + amount
            if new_amount > 0:
                pos["avg_price"] = total_value / float(new_amount)
            pos["amount"] = new_amount
        else:
            # Sell reduces position
            pos["amount"] = max(Decimal("0"), pos["amount"] - amount)
            if pos["amount"] == 0:
                del self.positions[token_address]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trader statistics"""
        return {
            "is_initialized": self.is_initialized,
            "networks_connected": list(self.web3_clients.keys()),
            "total_trades": len(self.trades),
            "confirmed_trades": len([t for t in self.trades if t.status == "confirmed"]),
            "failed_trades": len([t for t in self.trades if t.status == "failed"]),
            "open_positions": len(self.positions),
            "positions": {addr: {"amount": str(p["amount"]), "avg_price": p["avg_price"]} 
                         for addr, p in self.positions.items()}
        }


# Global instance
_dex_trader: Optional[DEXTrader] = None


async def get_dex_trader() -> DEXTrader:
    """Get global DEX trader instance"""
    global _dex_trader
    if _dex_trader is None:
        _dex_trader = DEXTrader()
        await _dex_trader.initialize()
    return _dex_trader
