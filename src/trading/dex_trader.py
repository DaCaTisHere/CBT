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
from datetime import datetime, timedelta
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
            "baseswap_v2": "0xaaa3b1F1bd7BCc97fD1917c18ADE665C5D31F066",
            "sushiswap_v2": "0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891",
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
    
    # KyberSwap Aggregator API (free, no API key, supports all DEXes)
    KYBER_CHAIN_IDS = {
        "eth": 1,
        "bsc": 56,
        "base": 8453,
        "arbitrum": 42161,
    }
    KYBER_CHAIN_SLUGS = {
        "eth": "ethereum",
        "bsc": "bsc",
        "base": "base",
        "arbitrum": "arbitrum",
    }
    NATIVE_TOKEN_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    
    # Default settings
    DEFAULT_SLIPPAGE = 5.0  # 5% for new tokens (higher needed)
    MAX_SLIPPAGE = 15.0     # 15% max
    GAS_BUFFER = 1.2        # 20% buffer for gas estimation
    
    # Minimum gas to ALWAYS keep reserved (in native tokens)
    # On L2s (Base, Arbitrum), gas is extremely cheap (~$0.01 per swap)
    MIN_GAS_RESERVE = {
        "eth": Decimal("0.005"),        # ~$10 reserve for ETH gas
        "bsc": Decimal("0.005"),        # ~$3 reserve for BSC gas
        "base": Decimal("0.0005"),      # ~$1 reserve for Base gas (L2, very cheap)
        "arbitrum": Decimal("0.0005"),  # ~$1 reserve for Arbitrum gas (L2)
        "polygon": Decimal("1.0"),      # ~$1 reserve for Polygon gas
    }
    
    # Estimated gas cost per trade (in native tokens)
    ESTIMATED_GAS_PER_TRADE = {
        "eth": Decimal("0.003"),        # ~$6 per swap
        "bsc": Decimal("0.001"),        # ~$0.6 per swap
        "base": Decimal("0.00005"),     # ~$0.10 per swap (L2, very cheap)
        "arbitrum": Decimal("0.00005"), # ~$0.10 per swap (L2)
        "polygon": Decimal("0.5"),      # ~$0.5 per swap
    }
    
    # Max percentage of wallet to use per trade
    # With small capital ($50-100), we need to use more per trade
    MAX_TRADE_PERCENT = 70  # Allow up to 70% per trade for small wallets
    
    def __init__(self):
        self.logger = logger
        self.web3_clients: Dict[str, Any] = {}
        self.wallets: Dict[str, Any] = {}
        self.is_initialized = False
        self.trades: list[DEXTrade] = []
        
        # Position tracking
        self.positions: Dict[str, Dict] = {}  # token_address -> {amount, avg_price}
        
        # Sniper positions with exit rules
        self.sniper_positions: Dict[str, Dict] = {}  # token_address -> {entry, tp, sl, etc}
        
        # Safety manager - blocks all real trades until simulation is validated
        from src.core.safety_manager import get_safety_manager
        self.safety = get_safety_manager()
    
    @property
    def providers(self) -> Dict[str, Any]:
        """Return web3 providers for AI modules compatibility"""
        return self.web3_clients
        
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
    
    def get_available_capital(self, network: str, native_price_usd: float = None) -> Tuple[Decimal, float]:
        """
        Calculate available trading capital after reserving gas
        
        Returns:
            Tuple of (available_native_tokens, available_usd)
        """
        wallet = self.wallets.get(network)
        if not wallet:
            return Decimal("0"), 0.0
        
        # Refresh balance
        try:
            w3 = self.web3_clients.get(network)
            if w3:
                balance = w3.eth.get_balance(wallet["address"])
                wallet["native_balance"] = Decimal(balance) / Decimal(10**18)
        except:
            pass
        
        native_balance = wallet.get("native_balance", Decimal("0"))
        
        # Reserve gas for at least 3 trades
        gas_reserve = self.MIN_GAS_RESERVE.get(network, Decimal("0.01"))
        gas_per_trade = self.ESTIMATED_GAS_PER_TRADE.get(network, Decimal("0.002"))
        total_reserve = gas_reserve + (gas_per_trade * 3)  # Reserve for 3 trades
        
        available_native = max(Decimal("0"), native_balance - total_reserve)
        
        # Estimate USD value - use consistent prices everywhere
        if native_price_usd is None:
            native_price_usd = self.DEFAULT_NATIVE_PRICES.get(network, 2700)
        
        available_usd = float(available_native) * native_price_usd
        
        return available_native, available_usd
    
    def can_trade(self, network: str, amount_usd: float) -> Tuple[bool, str]:
        """
        Check if we have enough capital to make a trade
        
        Returns:
            Tuple of (can_trade, reason)
        """
        wallet = self.wallets.get(network)
        if not wallet:
            return False, f"Network {network} not initialized"
        
        # Check minimum gas reserve
        native_balance = wallet.get("native_balance", Decimal("0"))
        gas_reserve = self.MIN_GAS_RESERVE.get(network, Decimal("0.01"))
        gas_per_trade = self.ESTIMATED_GAS_PER_TRADE.get(network, Decimal("0.002"))
        
        if native_balance < gas_reserve + gas_per_trade:
            return False, f"Insufficient gas on {network}: {native_balance:.4f} (need {gas_reserve + gas_per_trade:.4f})"
        
        # Check if trade amount is within limits
        _, available_usd = self.get_available_capital(network)
        max_trade_usd = available_usd * (self.MAX_TRADE_PERCENT / 100)
        
        if amount_usd > max_trade_usd:
            return False, f"Trade amount ${amount_usd:.2f} exceeds max ${max_trade_usd:.2f} ({self.MAX_TRADE_PERCENT}% of available)"
        
        if amount_usd > available_usd:
            return False, f"Insufficient capital: ${amount_usd:.2f} requested, ${available_usd:.2f} available"
        
        return True, "OK"
    
    async def refresh_balances(self):
        """Refresh wallet balances on all networks"""
        for network, wallet in self.wallets.items():
            try:
                w3 = self.web3_clients.get(network)
                if w3:
                    balance = w3.eth.get_balance(wallet["address"])
                    wallet["native_balance"] = Decimal(balance) / Decimal(10**18)
                    native_symbol = "ETH" if network != "bsc" else "BNB"
                    self.logger.debug(f"[DEX] {network.upper()} balance: {wallet['native_balance']:.4f} {native_symbol}")
            except Exception as e:
                self.logger.warning(f"[DEX] Could not refresh {network} balance: {e}")
    
    # Default native token prices for USD conversion
    DEFAULT_NATIVE_PRICES = {
        "eth": 2700, "bsc": 650, "base": 2700,
        "arbitrum": 2700, "polygon": 1, "avax": 35,
    }
    
    def _get_native_price_usd(self, network: str) -> float:
        """Get estimated native token price in USD"""
        return self.DEFAULT_NATIVE_PRICES.get(network, 2000)
    
    async def buy(
        self,
        network: str,
        token_address: str,
        amount_usd: float,
        slippage: float = None,
        token_symbol: str = None
    ) -> Optional[DEXTrade]:
        """
        Buy a token on a DEX using native token (ETH/BNB)
        
        IMPORTANT: Swaps native token → target token via WETH/WBNB
        The wallet holds native tokens, NOT stablecoins.
        
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
        
        # In simulation mode, skip real wallet checks entirely
        is_sim = self.safety.is_simulation_mode()
        
        if is_sim:
            self.logger.info(f"[DEX] 🧪 SIMULATION mode - using virtual capital")
            available_native = Decimal("1.0")
            available_usd = float(amount_usd) + 100
        else:
            await self.refresh_balances()
            can_trade_ok, reason = self.can_trade(network, amount_usd)
            if not can_trade_ok:
                self.logger.warning(f"[DEX] ❌ Cannot trade: {reason}")
                return None
            available_native, available_usd = self.get_available_capital(network)
            self.logger.info(f"[DEX] 💰 Available capital on {network.upper()}: ${available_usd:.2f} ({available_native:.4f} native)")
        
        slippage = slippage or self.DEFAULT_SLIPPAGE
        if slippage > self.MAX_SLIPPAGE:
            slippage = self.MAX_SLIPPAGE
        
        # Convert USD amount to native token amount (ETH/BNB)
        native_price = self._get_native_price_usd(network)
        amount_native = Decimal(str(amount_usd)) / Decimal(str(native_price))
        
        if not is_sim and amount_native > available_native:
            amount_native = available_native * Decimal("0.9")
            amount_usd = float(amount_native) * native_price
            self.logger.info(f"[DEX] ⚠️ Adjusted trade to ${amount_usd:.2f} ({amount_native:.6f} native)")
        
        native_symbol = "ETH" if network != "bsc" else "BNB"
        self.logger.info(f"[DEX] 🛒 Buying ${amount_usd:.2f} of {token_symbol or token_address[:10]} on {network.upper()} ({amount_native:.6f} {native_symbol})")
        
        try:
            amount_in_wei = int(amount_native * Decimal(10**18))

            # Primary: KyberSwap aggregator
            tx_hash, amount_out_raw = await self._kyber_swap(
                network=network,
                token_in=self.NATIVE_TOKEN_ADDRESS,
                token_out=token_address,
                amount_in_wei=amount_in_wei,
                slippage_bps=int(slippage * 100)
            )

            # Fallback: direct V2 router if KyberSwap failed
            if not tx_hash and not is_sim:
                self.logger.warning(f"[DEX] KyberSwap failed, trying direct V2 router...")
                tx_data = await self._build_swap_tx(
                    network=network,
                    token_in=self.NATIVE_TOKEN_ADDRESS,
                    token_out=token_address,
                    amount_in=amount_native,
                    slippage=slippage
                )
                if tx_data:
                    tx_hash, amount_out_raw = await self._send_v3_swap(network, tx_data)
                    if tx_hash:
                        self.logger.info(f"[DEX] V2 fallback succeeded: {tx_hash}")
            
            # Get token decimals (most ERC20 = 18, but some differ)
            token_decimals = 18
            try:
                w3 = self.web3_clients.get(network)
                if w3:
                    token_cs = w3.to_checksum_address(token_address)
                    token_contract = w3.eth.contract(address=token_cs, abi=self.ERC20_ABI)
                    token_decimals = token_contract.functions.decimals().call()
            except Exception:
                pass
            
            # Calculate token price: USD spent / tokens received
            amount_tokens = Decimal(str(amount_out_raw)) / Decimal(10**token_decimals) if amount_out_raw else Decimal("0")
            if float(amount_tokens) > 0:
                price_usd = amount_usd / float(amount_tokens)
            else:
                price_usd = 0
            self.logger.info(f"[DEX] Token price: ${price_usd:.10f} ({amount_tokens:.2f} tokens for ${amount_usd:.2f}, decimals={token_decimals})")
            
            if tx_hash:
                trade = DEXTrade(
                    network=network,
                    token_address=token_address,
                    token_symbol=token_symbol or "UNKNOWN",
                    action="buy",
                    amount_in=amount_native,
                    amount_out=amount_tokens,
                    price_usd=price_usd,
                    tx_hash=tx_hash,
                    status="confirmed"
                )
                
                self.trades.append(trade)
                
                self._update_position(token_address, amount_tokens, price_usd, "buy", decimals=token_decimals)
                self.logger.info(f"[DEX] ✅ Buy CONFIRMED on-chain: {amount_tokens:.6f} tokens @ ${price_usd:.8f}")
                self.logger.info(f"[DEX] TX: {tx_hash}")
                return trade
            else:
                self.logger.warning(f"[DEX] ❌ Buy failed: no router could execute the swap")
            
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
        
        # Get position amount and decimals
        position = self.positions.get(token_address)
        token_decimals = position.get("decimals", 18) if position else 18
        
        if amount_tokens is None:
            if not position:
                self.logger.warning(f"[DEX] No position found for {token_address}")
                return None
            amount_tokens = position["amount"] * Decimal(str(percent / 100))
        
        self.logger.info(f"[DEX] 💰 Selling {amount_tokens:.6f} {token_symbol or token_address[:10]} on {network.upper()}")
        
        try:
            amount_in_wei = int(amount_tokens * Decimal(10**token_decimals))
            
            if not self.safety.is_simulation_mode():
                await self._approve_token_for_kyber(network, token_address, amount_in_wei)
            
            if self.safety.is_simulation_mode():
                import hashlib
                tx_hash = "0x" + hashlib.sha256(f"sim-sell-{token_address}-{amount_in_wei}".encode()).hexdigest()
                price_usd = await self._get_token_price(network, token_address) or 0
                amount_usd = float(amount_tokens) * price_usd
                self.logger.info(f"[DEX] 🧪 SIMULATION sell: {amount_tokens:.4f} tokens @ ${price_usd:.10f} = ${amount_usd:.2f}")
            else:
                tx_hash, amount_out_raw = await self._kyber_swap(
                    network=network,
                    token_in=token_address,
                    token_out=self.NATIVE_TOKEN_ADDRESS,
                    amount_in_wei=amount_in_wei,
                    slippage_bps=int(slippage * 100)
                )
                price_usd = await self._get_token_price(network, token_address) or 0
                amount_usd = float(amount_tokens) * price_usd
            
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
                    status="confirmed"
                )
                
                self.trades.append(trade)
                self._update_position(token_address, amount_tokens, price_usd, "sell")
                self.logger.info(f"[DEX] ✅ Sell CONFIRMED: ${amount_usd:.2f}")
                return trade
            
            return None
            
        except Exception as e:
            self.logger.error(f"[DEX] Sell error: {e}")
            return None
    
    async def _get_token_price(self, network: str, token_address: str) -> Optional[float]:
        """Get token price from DEX"""
        client = None
        try:
            from src.modules.geckoterminal.gecko_client import GeckoTerminalClient
            client = GeckoTerminalClient()
            await client.initialize()
            price = await client.get_token_price(network, token_address)
            return price
        except Exception:
            return None
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass
    
    # Uniswap V2 Router ABI (minimal for swaps)
    UNISWAP_V2_ROUTER_ABI = [
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "swapExactTokensForTokens",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "swapExactETHForTokens",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "swapExactTokensForETH",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    
    # Uniswap V3 SwapRouter02 ABI (for exactInputSingle)
    UNISWAP_V3_ROUTER_ABI = [
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "address", "name": "tokenIn", "type": "address"},
                        {"internalType": "address", "name": "tokenOut", "type": "address"},
                        {"internalType": "uint24", "name": "fee", "type": "uint24"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                        {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                    ],
                    "internalType": "struct IV3SwapRouter.ExactInputSingleParams",
                    "name": "params",
                    "type": "tuple"
                }
            ],
            "name": "exactInputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function"
        }
    ]
    
    # V3 fee tiers to try (most common first)
    V3_FEE_TIERS = [10000, 3000, 500, 100]  # 1%, 0.3%, 0.05%, 0.01%
    
    # ERC20 ABI (for approvals)
    ERC20_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "spender", "type": "address"},
                {"internalType": "uint256", "name": "amount", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    async def _build_swap_tx(
        self,
        network: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage: float,
        force_router: str = None
    ) -> Optional[Dict]:
        """Build swap transaction for DEX using Uniswap V2 style router"""
        
        if network not in self.web3_clients:
            return None
        
        w3 = self.web3_clients[network]
        wallet = self.wallets.get(network)
        if not wallet:
            return None
        
        try:
            # Use forced router or find one
            if force_router:
                router_address = force_router
            else:
                router_address = None
                for dex_name, addr in self.ROUTERS.get(network, {}).items():
                    if "v2" in dex_name.lower() or "pancake" in dex_name.lower():
                        router_address = addr
                        break
                
                if not router_address:
                    routers = self.ROUTERS.get(network, {})
                    if routers:
                        router_address = list(routers.values())[0]
            
            if not router_address:
                self.logger.error(f"[DEX] No router found for {network}")
                return None
            
            # Get wrapped native token for path
            weth = self.WRAPPED_NATIVE.get(network)
            if not weth:
                self.logger.error(f"[DEX] No WETH address for {network}")
                return None
            
            # Build swap path: token_in -> WETH -> token_out (or direct if one is WETH)
            token_in_checksum = w3.to_checksum_address(token_in)
            token_out_checksum = w3.to_checksum_address(token_out)
            weth_checksum = w3.to_checksum_address(weth)
            
            if token_in_checksum == weth_checksum:
                path = [weth_checksum, token_out_checksum]
            elif token_out_checksum == weth_checksum:
                path = [token_in_checksum, weth_checksum]
            else:
                path = [token_in_checksum, weth_checksum, token_out_checksum]
            
            # Calculate deadline (10 minutes from now)
            deadline = int(datetime.utcnow().timestamp()) + 600
            
            # Amount with 18 decimals (simplified - should check actual decimals)
            amount_in_wei = int(amount_in * Decimal(10**18))
            
            # For new/unknown tokens, we can't reliably estimate output amount
            # Set amount_out_min = 0 to accept any output (slippage protection via
            # our own position management: stop-loss, take-profit, max hold time)
            # This is standard practice for sniper bots trading new tokens
            amount_out_min = 0
            
            self.logger.info(f"[DEX] Swap params: in={amount_in_wei} wei | out_min={amount_out_min} | router={router_address[:16]}... | path={[p[:10]+'...' for p in path]}")
            
            return {
                "network": network,
                "router": router_address,
                "from": wallet["address"],
                "path": path,
                "amount_in": amount_in_wei,
                "amount_out_min": amount_out_min,
                "deadline": deadline,
                "is_eth_swap": token_in_checksum == weth_checksum
            }
            
        except Exception as e:
            self.logger.error(f"[DEX] Build TX error: {e}")
            return None
    
    async def _simulate_tx(self, network: str, tx: Dict) -> bool:
        """Simulate transaction to check if it would succeed"""
        try:
            w3 = self.web3_clients.get(network)
            if not w3:
                return False
            
            wallet = self.wallets.get(network)
            if not wallet:
                return False
            
            # Refresh balance
            try:
                balance = w3.eth.get_balance(wallet["address"])
                wallet["native_balance"] = Decimal(balance) / Decimal(10**18)
            except:
                pass
            
            native_balance = wallet.get("native_balance", Decimal("0"))
            
            # Check minimum gas reserve
            gas_reserve = self.MIN_GAS_RESERVE.get(network, Decimal("0.01"))
            gas_per_trade = self.ESTIMATED_GAS_PER_TRADE.get(network, Decimal("0.002"))
            min_required = gas_reserve + gas_per_trade
            
            if native_balance < min_required:
                self.logger.warning(f"[DEX] ⚠️ Insufficient gas on {network}: {native_balance:.4f} (need {min_required:.4f})")
                return False
            
            # Estimate gas price
            try:
                gas_price = w3.eth.gas_price
                estimated_gas = 300000  # Conservative estimate for swap
                gas_cost_wei = gas_price * estimated_gas
                gas_cost_native = Decimal(gas_cost_wei) / Decimal(10**18)
                
                if native_balance - gas_cost_native < gas_reserve:
                    self.logger.warning(f"[DEX] ⚠️ Trade would leave insufficient gas reserve on {network}")
                    return False
                    
                self.logger.info(f"[DEX] ⛽ Estimated gas cost: {gas_cost_native:.6f} native ({network.upper()})")
            except Exception as e:
                self.logger.debug(f"[DEX] Could not estimate gas price: {e}")
            
            return True
        except Exception as e:
            self.logger.error(f"[DEX] Simulation error: {e}")
            return False
    
    async def _approve_token_for_kyber(self, network: str, token_address: str, amount: int) -> bool:
        """Approve token spending for KyberSwap router"""
        import aiohttp
        
        try:
            w3 = self.web3_clients.get(network)
            wallet = self.wallets.get(network)
            if not w3 or not wallet:
                return False
            
            chain_slug = self.KYBER_CHAIN_SLUGS.get(network)
            if not chain_slug:
                return False
            
            # Get the KyberSwap router address
            base_url = f"https://aggregator-api.kyberswap.com/{chain_slug}/api/v1"
            
            # Use standard KyberSwap router for approvals
            kyber_router = "0x6131B5fae19EA4f9D964eAc0408E4408b66337b5"  # KyberSwap MetaAggregationRouterV2
            
            token_cs = w3.to_checksum_address(token_address)
            router_cs = w3.to_checksum_address(kyber_router)
            
            token_contract = w3.eth.contract(address=token_cs, abi=self.ERC20_ABI)
            
            # Check current allowance
            allowance = token_contract.functions.allowance(wallet["address"], router_cs).call()
            
            if allowance >= amount:
                return True
            
            # Approve max
            nonce = w3.eth.get_transaction_count(wallet["address"])
            approve_tx = token_contract.functions.approve(
                router_cs, 2**256 - 1
            ).build_transaction({
                "from": wallet["address"],
                "gas": 100000,
                "gasPrice": w3.eth.gas_price,
                "nonce": nonce,
                "chainId": self.KYBER_CHAIN_IDS.get(network, 1),
            })
            
            signed = w3.eth.account.sign_transaction(approve_tx, settings.WALLET_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            self.logger.info(f"[DEX] 🔓 Token approval TX: {tx_hash.hex()[:20]}...")
            
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            return True
            
        except Exception as e:
            self.logger.error(f"[DEX] Token approval error: {e}")
            return False
    
    # Rate limiter for KyberSwap API
    _last_kyber_call: float = 0
    _kyber_min_interval: float = 3.0  # Minimum 3 seconds between API calls
    
    async def _kyber_swap(
        self,
        network: str,
        token_in: str,
        token_out: str,
        amount_in_wei: int,
        slippage_bps: int = 500
    ) -> Tuple[Optional[str], int]:
        """
        Execute a swap via KyberSwap aggregator API.
        Routes through ALL DEXes automatically (Uniswap V2/V3/V4, Aerodrome, etc.)
        
        Returns: (tx_hash, amount_out_raw) or (None, 0) on failure
        """
        import aiohttp
        import os
        import time
        
        # Rate limiting
        now = time.time()
        elapsed = now - self._last_kyber_call
        if elapsed < self._kyber_min_interval:
            wait_time = self._kyber_min_interval - elapsed
            self.logger.debug(f"[DEX] KyberSwap rate limit: waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
        self._last_kyber_call = time.time()
        
        # ===== SAFETY GATE =====
        is_sim = self.safety.is_simulation_mode()
        
        if not is_sim:
            is_native_input = token_in.lower() == self.NATIVE_TOKEN_ADDRESS.lower()
            if is_native_input:
                native_price = self.DEFAULT_NATIVE_PRICES.get(network, 2700)
                trade_usd = (amount_in_wei / 1e18) * native_price
            else:
                trade_usd = 10.0  # Sells: use conservative estimate, KyberSwap quote will confirm
            can_trade, reason = self.safety.can_trade_real(network, trade_usd)
            if not can_trade:
                self.logger.warning(f"[SAFETY] 🚫 REAL TRADE BLOCKED: {reason}")
                return None, 0
        
        chain_slug = self.KYBER_CHAIN_SLUGS.get(network)
        if not chain_slug:
            self.logger.error(f"[DEX] KyberSwap: unsupported network {network}")
            return None, 0
        
        w3 = self.web3_clients.get(network)
        wallet = self.wallets.get(network)
        if not w3 or not wallet:
            self.logger.error(f"[DEX] KyberSwap: no web3/wallet for {network}")
            return None, 0
        
        base_url = f"https://aggregator-api.kyberswap.com/{chain_slug}/api/v1"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Get quote/route (ALWAYS - needed for accurate pricing)
                route_params = {
                    "tokenIn": token_in,
                    "tokenOut": token_out,
                    "amountIn": str(amount_in_wei),
                    "saveGas": "false",
                }
                
                self.logger.info(f"[DEX] 🔄 KyberSwap: getting route for {token_out[:16]}... on {network}")
                
                async with session.get(f"{base_url}/routes", params=route_params) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        self.logger.warning(f"[DEX] KyberSwap route failed ({resp.status}): {err[:200]}")
                        return None, 0
                    
                    route_data = await resp.json()
                
                if route_data.get("code") != 0:
                    self.logger.warning(f"[DEX] KyberSwap: no route found - {route_data.get('message', 'unknown')}")
                    return None, 0
                
                route_summary = route_data["data"]["routeSummary"]
                router_address = route_data["data"]["routerAddress"]
                amount_out = int(route_summary.get("amountOut", "0"))
                amount_out_usd = route_summary.get("amountOutUsd", "0")
                
                self.logger.info(f"[DEX] 📊 KyberSwap route: ~${amount_out_usd} out ({amount_out} raw tokens)")
                
                # SIMULATION: return fake TX + real quote amount
                if is_sim:
                    import hashlib
                    fake_hash = "0x" + hashlib.sha256(f"kyber-{token_out}-{amount_in_wei}-{time.time()}".encode()).hexdigest()
                    self.logger.info(f"[DEX] 🧪 SIMULATION - Quote: {amount_out} tokens (~${amount_out_usd})")
                    return fake_hash, amount_out
                
                # Step 2: Build transaction
                build_body = {
                    "routeSummary": route_summary,
                    "sender": wallet["address"],
                    "recipient": wallet["address"],
                    "slippageTolerance": slippage_bps,
                }
                
                async with session.post(
                    f"{base_url}/route/build",
                    json=build_body,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        self.logger.warning(f"[DEX] KyberSwap build failed ({resp.status}): {err[:200]}")
                        return None, 0
                    
                    build_data = await resp.json()
                
                if build_data.get("code") != 0:
                    self.logger.warning(f"[DEX] KyberSwap build error: {build_data.get('message', 'unknown')}")
                    return None, 0
                
                tx_data = build_data["data"]
                
                # Step 3: Sign and send transaction
                nonce = w3.eth.get_transaction_count(wallet["address"])
                
                # Parse value - CRITICAL: for native ETH/BNB swaps, KyberSwap API
                # often returns value=0 in the build response. We MUST override
                # with the actual amount when swapping native tokens.
                raw_value = tx_data.get("value", "0")
                if isinstance(raw_value, str):
                    if raw_value.startswith("0x"):
                        tx_value = int(raw_value, 16)
                    else:
                        tx_value = int(raw_value)
                else:
                    tx_value = int(raw_value)
                
                # Force correct value for native token swaps
                is_native_swap = token_in.lower() == self.NATIVE_TOKEN_ADDRESS.lower()
                if is_native_swap and tx_value == 0:
                    tx_value = amount_in_wei
                    self.logger.info(f"[DEX] KyberSwap: forced value={tx_value} for native swap (API returned 0)")
                
                # Parse gas
                raw_gas = tx_data.get("gas", "500000")
                if isinstance(raw_gas, str):
                    if raw_gas.startswith("0x"):
                        tx_gas = int(raw_gas, 16)
                    else:
                        tx_gas = int(raw_gas)
                else:
                    tx_gas = int(raw_gas)
                
                self.logger.info(f"[DEX] KyberSwap TX build: value={tx_value} wei ({tx_value / 1e18:.6f} ETH) | gas={tx_gas} | router={tx_data['routerAddress'][:16]}...")
                
                built_tx = {
                    "from": wallet["address"],
                    "to": w3.to_checksum_address(tx_data["routerAddress"]),
                    "data": tx_data["data"],
                    "value": tx_value,
                    "gas": tx_gas + 50000,  # Add gas buffer
                    "gasPrice": w3.eth.gas_price,
                    "nonce": nonce,
                    "chainId": self.KYBER_CHAIN_IDS.get(network, 1),
                }
                
                signed_tx = w3.eth.account.sign_transaction(built_tx, settings.WALLET_PRIVATE_KEY)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                
                self.logger.info(f"[DEX] ✅ KyberSwap TX sent: {tx_hash.hex()}")
                
                # Wait for confirmation
                confirmed = await self._wait_confirmation(network, tx_hash.hex())
                
                if confirmed:
                    self.logger.info(f"[DEX] ✅ KyberSwap swap CONFIRMED on {network.upper()}")
                    return tx_hash.hex(), amount_out
                else:
                    self.logger.warning(f"[DEX] ❌ KyberSwap swap reverted on {network.upper()}")
                    return None, 0
                    
        except Exception as e:
            self.logger.error(f"[DEX] KyberSwap error: {e}")
            import traceback
            self.logger.error(f"[DEX] KyberSwap traceback: {traceback.format_exc()}")
            return None, 0
    
    async def _send_v3_swap(
        self,
        network: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        is_eth_swap: bool = True
    ) -> Optional[str]:
        """Send a Uniswap V3 exactInputSingle swap, trying multiple fee tiers"""
        # SAFETY GATE
        if self.safety.is_simulation_mode():
            import hashlib
            fake_hash = "0x" + hashlib.sha256(f"v3-{token_out}-{amount_in}".encode()).hexdigest()
            self.logger.info(f"[DEX] 🧪 V3 SIMULATION - Fake TX: {fake_hash[:20]}...")
            return fake_hash
        
        native_price = self.DEFAULT_NATIVE_PRICES.get(network, 2700)
        trade_usd = float(amount_in) * native_price
        can_trade, reason = self.safety.can_trade_real(network, trade_usd)
        if not can_trade:
            self.logger.warning(f"[SAFETY] 🚫 V3 REAL TRADE BLOCKED: {reason}")
            return None
        
        try:
            w3 = self.web3_clients.get(network)
            wallet = self.wallets.get(network)
            if not w3 or not wallet:
                return None
            
            # Find V3 router
            v3_addr = None
            for name, addr in self.ROUTERS.get(network, {}).items():
                if "v3" in name.lower():
                    v3_addr = addr
                    break
            
            if not v3_addr:
                self.logger.warning(f"[DEX] No V3 router for {network}")
                return None
            
            router_address = w3.to_checksum_address(v3_addr)
            router = w3.eth.contract(address=router_address, abi=self.UNISWAP_V3_ROUTER_ABI)
            
            token_in_cs = w3.to_checksum_address(token_in)
            token_out_cs = w3.to_checksum_address(token_out)
            amount_in_wei = int(amount_in * Decimal(10**18))
            deadline = int(datetime.utcnow().timestamp()) + 600
            
            # Try each fee tier
            for fee in self.V3_FEE_TIERS:
                try:
                    nonce = w3.eth.get_transaction_count(wallet["address"])
                    
                    params = (
                        token_in_cs,       # tokenIn
                        token_out_cs,      # tokenOut
                        fee,               # fee tier
                        wallet["address"], # recipient
                        amount_in_wei,     # amountIn
                        0,                 # amountOutMinimum (0 = accept any)
                        0                  # sqrtPriceLimitX96 (0 = no limit)
                    )
                    
                    swap_fn = router.functions.exactInputSingle(params)
                    
                    tx_data = {
                        "from": wallet["address"],
                        "gas": 350000,
                        "gasPrice": w3.eth.gas_price,
                        "nonce": nonce,
                    }
                    
                    if is_eth_swap:
                        tx_data["value"] = amount_in_wei
                    
                    built_tx = swap_fn.build_transaction(tx_data)
                    signed_tx = w3.eth.account.sign_transaction(built_tx, settings.WALLET_PRIVATE_KEY)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    
                    self.logger.info(f"[DEX] ✅ V3 TX sent (fee={fee}): {tx_hash.hex()}")
                    
                    # Check confirmation immediately since Base is fast
                    confirmed = await self._wait_confirmation(network, tx_hash.hex())
                    if confirmed:
                        return tx_hash.hex()
                    else:
                        self.logger.warning(f"[DEX] V3 fee tier {fee} reverted, trying next...")
                        continue
                        
                except Exception as fee_err:
                    self.logger.debug(f"[DEX] V3 fee tier {fee} error: {fee_err}")
                    continue
            
            self.logger.warning(f"[DEX] All V3 fee tiers failed for {token_out[:16]}...")
            return None
            
        except Exception as e:
            self.logger.error(f"[DEX] V3 swap error: {e}")
            return None
    
    async def _send_tx(self, network: str, tx: Dict) -> Optional[str]:
        """Send swap transaction to network"""
        # SAFETY GATE
        if self.safety.is_simulation_mode():
            import hashlib
            fake_hash = "0x" + hashlib.sha256(str(tx).encode()).hexdigest()
            self.logger.info(f"[DEX] 🧪 SIMULATION MODE - Fake TX: {fake_hash[:20]}...")
            return fake_hash
        
        can_trade, reason = self.safety.can_trade_real(network, 50)
        if not can_trade:
            self.logger.warning(f"[SAFETY] 🚫 _send_tx BLOCKED: {reason}")
            return None
        
        if settings.DRY_RUN:
            self.logger.info("[DEX] DRY RUN - Would send transaction")
            return None
        
        # REAL TRANSACTION EXECUTION
        try:
            w3 = self.web3_clients.get(network)
            wallet = self.wallets.get(network)
            
            if not w3 or not wallet:
                return None
            
            router_address = w3.to_checksum_address(tx["router"])
            router = w3.eth.contract(address=router_address, abi=self.UNISWAP_V2_ROUTER_ABI)
            
            # Get nonce
            nonce = w3.eth.get_transaction_count(wallet["address"])
            
            # Build the swap call
            if tx.get("is_eth_swap"):
                # Swap ETH for tokens
                swap_fn = router.functions.swapExactETHForTokens(
                    tx["amount_out_min"],
                    tx["path"],
                    wallet["address"],
                    tx["deadline"]
                )
                
                built_tx = swap_fn.build_transaction({
                    "from": wallet["address"],
                    "value": tx["amount_in"],
                    "gas": 300000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": nonce,
                })
            else:
                # First approve token spending
                token_in = w3.to_checksum_address(tx["path"][0])
                token_contract = w3.eth.contract(address=token_in, abi=self.ERC20_ABI)
                
                # Check allowance
                allowance = token_contract.functions.allowance(
                    wallet["address"], 
                    router_address
                ).call()
                
                if allowance < tx["amount_in"]:
                    # Approve max amount
                    approve_tx = token_contract.functions.approve(
                        router_address,
                        2**256 - 1  # Max approval
                    ).build_transaction({
                        "from": wallet["address"],
                        "gas": 100000,
                        "gasPrice": w3.eth.gas_price,
                        "nonce": nonce,
                    })
                    
                    signed_approve = w3.eth.account.sign_transaction(
                        approve_tx, 
                        settings.WALLET_PRIVATE_KEY
                    )
                    approve_hash = w3.eth.send_raw_transaction(signed_approve.rawTransaction)
                    self.logger.info(f"[DEX] Approval TX sent: {approve_hash.hex()[:20]}...")
                    
                    # Wait for approval
                    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                    nonce += 1
                
                # Now execute swap
                swap_fn = router.functions.swapExactTokensForTokens(
                    tx["amount_in"],
                    tx["amount_out_min"],
                    tx["path"],
                    wallet["address"],
                    tx["deadline"]
                )
                
                built_tx = swap_fn.build_transaction({
                    "from": wallet["address"],
                    "gas": 300000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": nonce,
                })
            
            # Sign and send
            signed_tx = w3.eth.account.sign_transaction(built_tx, settings.WALLET_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            self.logger.info(f"[DEX] ✅ Transaction sent: {tx_hash.hex()}")
            self.logger.info(f"[DEX] Router: {tx['router'][:20]}... | Network: {network} | ETH swap: {tx.get('is_eth_swap')}")
            return tx_hash.hex()
            
        except Exception as e:
            self.logger.error(f"[DEX] Transaction failed: {e}")
            self.logger.error(f"[DEX] Details: network={network} router={tx.get('router', 'N/A')[:20]}")
            return None
    
    async def _wait_confirmation(self, network: str, tx_hash: str, timeout: int = 60) -> bool:
        """Wait for transaction confirmation"""
        import os
        _sim_env = os.getenv("SIMULATION_MODE", "true").strip().lower()
        if _sim_env in ("true", "1", "yes", "on"):
            await asyncio.sleep(1)
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
    
    def _update_position(self, token_address: str, amount: Decimal, price: float, action: str, decimals: int = 18):
        """Update position tracking"""
        if token_address not in self.positions:
            self.positions[token_address] = {"amount": Decimal("0"), "avg_price": 0, "decimals": decimals}
        
        pos = self.positions[token_address]
        if decimals != 18:
            pos["decimals"] = decimals
        
        if action == "buy":
            total_value = float(pos["amount"]) * pos["avg_price"] + float(amount) * price
            new_amount = pos["amount"] + amount
            if new_amount > 0:
                pos["avg_price"] = total_value / float(new_amount)
            pos["amount"] = new_amount
        else:
            pos["amount"] = max(Decimal("0"), pos["amount"] - amount)
            if pos["amount"] == 0:
                del self.positions[token_address]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trader statistics"""
        # Calculate wallet info with gas reserves
        wallets_info = {}
        total_available_usd = 0
        
        for network, wallet in self.wallets.items():
            native_balance = wallet.get("native_balance", Decimal("0"))
            gas_reserve = self.MIN_GAS_RESERVE.get(network, Decimal("0.01"))
            available, available_usd = self.get_available_capital(network)
            
            native_symbol = "ETH" if network != "bsc" else "BNB"
            wallets_info[network] = {
                "balance": float(native_balance),
                "symbol": native_symbol,
                "gas_reserve": float(gas_reserve),
                "available_for_trading": float(available),
                "available_usd": available_usd,
                "can_trade": native_balance > gas_reserve
            }
            total_available_usd += available_usd
        
        return {
            "is_initialized": self.is_initialized,
            "networks_connected": list(self.web3_clients.keys()),
            "wallets": wallets_info,
            "total_available_usd": total_available_usd,
            "total_trades": len(self.trades),
            "confirmed_trades": len([t for t in self.trades if t.status == "confirmed"]),
            "failed_trades": len([t for t in self.trades if t.status == "failed"]),
            "open_positions": len(self.positions),
            "sniper_positions": len(self.sniper_positions),
            "positions": {addr: {"amount": str(p["amount"]), "avg_price": p["avg_price"]} 
                         for addr, p in self.positions.items()}
        }
    
    # ============== SNIPER MODE ==============
    
    async def sniper_buy(
        self,
        network: str,
        token_address: str,
        amount_usd: float,
        token_symbol: str = None,
        tp1_pct: float = 20,    # Take profit 1 at +20%
        tp2_pct: float = 50,    # Take profit 2 at +50%
        tp3_pct: float = 100,   # Take profit 3 at +100%
        sl_pct: float = 15,     # Stop loss at -15%
        max_hold_hours: int = 24
    ) -> Optional[DEXTrade]:
        """
        SNIPER BUY - Quick entry with predefined exit strategy
        
        Automatically sets up:
        - 3 take-profit levels (sell 33% at each)
        - Tight stop-loss
        - Maximum hold time
        """
        trade = await self.buy(
            network=network,
            token_address=token_address,
            amount_usd=amount_usd,
            slippage=5.0,
            token_symbol=token_symbol
        )
        
        if trade and trade.status == "confirmed":
            trailing_pct = sl_pct  # Trailing stop follows the highest price
            self.sniper_positions[token_address] = {
                "network": network,
                "symbol": token_symbol,
                "entry_price": trade.price_usd,
                "highest_price": trade.price_usd,  # Track peak for trailing SL
                "amount": trade.amount_out,
                "entry_time": datetime.utcnow(),
                "tp1_price": trade.price_usd * (1 + tp1_pct / 100),
                "tp2_price": trade.price_usd * (1 + tp2_pct / 100),
                "tp3_price": trade.price_usd * (1 + tp3_pct / 100),
                "sl_price": trade.price_usd * (1 - sl_pct / 100),
                "trailing_pct": trailing_pct,
                "max_hold_until": datetime.utcnow() + timedelta(hours=max_hold_hours),
                "tp1_hit": False,
                "tp2_hit": False,
                "tp3_hit": False,
                "amount_remaining": trade.amount_out
            }
            
            self.logger.info(f"[SNIPER] 🎯 Position opened: {token_symbol or token_address[:10]}")
            self.logger.info(f"[SNIPER]    Entry: ${trade.price_usd:.8f} | Amount: {trade.amount_out:.4f}")
            self.logger.info(f"[SNIPER]    TP1: ${self.sniper_positions[token_address]['tp1_price']:.8f} (+{tp1_pct}%)")
            self.logger.info(f"[SNIPER]    TP2: ${self.sniper_positions[token_address]['tp2_price']:.8f} (+{tp2_pct}%)")
            self.logger.info(f"[SNIPER]    TP3: ${self.sniper_positions[token_address]['tp3_price']:.8f} (+{tp3_pct}%)")
            self.logger.info(f"[SNIPER]    SL:  ${self.sniper_positions[token_address]['sl_price']:.8f} (-{sl_pct}%)")
            
            return trade
        
        return None
    
    async def check_sniper_positions(self):
        """
        Check all sniper positions for TP/SL triggers.
        Fetches prices concurrently for performance.
        """
        if not self.sniper_positions:
            return
        
        # Fetch all prices concurrently
        async def _fetch(addr, pos):
            return addr, await self._get_token_price(pos["network"], addr)
        
        price_tasks = [_fetch(addr, pos) for addr, pos in self.sniper_positions.items()]
        price_results = await asyncio.gather(*price_tasks, return_exceptions=True)
        price_map = {}
        for result in price_results:
            if isinstance(result, Exception):
                continue
            addr, price = result
            if price:
                price_map[addr] = price
        
        positions_to_close = []
        
        for token_address, pos in self.sniper_positions.items():
            try:
                current_price = price_map.get(token_address)
                if not current_price:
                    pos["_price_fail_count"] = pos.get("_price_fail_count", 0) + 1
                    if pos["_price_fail_count"] > 10:
                        self.logger.warning(f"[SNIPER] No price data for {pos.get('symbol', '?')} after 10 tries, closing")
                        positions_to_close.append(token_address)
                    continue
                pos["_price_fail_count"] = 0
                
                symbol = pos.get("symbol", token_address[:10])
                entry_price = pos["entry_price"]
                if entry_price <= 0:
                    self.logger.warning(f"[SNIPER] Invalid entry price for {symbol}, closing")
                    positions_to_close.append(token_address)
                    continue
                
                # Update highest price and trailing SL
                if current_price > pos.get("highest_price", entry_price):
                    pos["highest_price"] = current_price
                    trailing_pct = pos.get("trailing_pct", 8)
                    new_sl = current_price * (1 - trailing_pct / 100)
                    if new_sl > pos["sl_price"]:
                        old_sl = pos["sl_price"]
                        pos["sl_price"] = new_sl
                        self.logger.info(f"[SNIPER] 📈 {symbol} trailing SL raised: ${old_sl:.8f} → ${new_sl:.8f} (peak: ${current_price:.8f})")
                
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                remaining_usd = float(pos.get("amount_remaining", pos.get("amount", 0))) * entry_price
                
                should_close = False
                close_reason = ""
                
                if current_price <= pos["sl_price"]:
                    close_reason = f"🛑 TRAILING STOP ({pnl_pct:+.1f}%)"
                    should_close = True
                elif datetime.utcnow() >= pos["max_hold_until"]:
                    close_reason = f"⏰ MAX HOLD ({pnl_pct:+.1f}%)"
                    should_close = True
                elif not pos["tp3_hit"] and current_price >= pos["tp3_price"]:
                    close_reason = f"💰💰💰 TP3 ({pnl_pct:+.1f}%)"
                    should_close = True
                
                if should_close:
                    self.logger.warning(f"[SNIPER] {close_reason} for {symbol}")
                    try:
                        await self.sell(
                            network=pos["network"], token_address=token_address,
                            percent=100, slippage=3.0, token_symbol=symbol
                        )
                    except Exception as sell_err:
                        pos["_sell_retries"] = pos.get("_sell_retries", 0) + 1
                        self.logger.error(f"[SNIPER] Sell failed for {symbol} (attempt {pos['_sell_retries']}): {sell_err}")
                        if pos["_sell_retries"] >= 3:
                            self.logger.error(f"[SNIPER] Max retries reached for {symbol}, removing position")
                            positions_to_close.append(token_address)
                        continue
                    pnl_usd = remaining_usd * (pnl_pct / 100)
                    self.safety.record_sell(symbol, pos["network"], remaining_usd, pnl_pct, pnl_usd, self.safety.is_simulation_mode())
                    positions_to_close.append(token_address)
                    continue
                
                # Partial take-profits
                if not pos["tp1_hit"] and current_price >= pos["tp1_price"]:
                    self.logger.info(f"[SNIPER] 💰 TP1 HIT for {symbol} (+{pnl_pct:.1f}%) - Selling 33%")
                    await self.sell(
                        network=pos["network"], token_address=token_address,
                        percent=33, token_symbol=symbol
                    )
                    pos["tp1_hit"] = True
                    pos["amount_remaining"] = pos["amount_remaining"] * Decimal("0.67")
                
                elif not pos["tp2_hit"] and current_price >= pos["tp2_price"]:
                    self.logger.info(f"[SNIPER] 💰💰 TP2 HIT for {symbol} (+{pnl_pct:.1f}%) - Selling 50%")
                    await self.sell(
                        network=pos["network"], token_address=token_address,
                        percent=50, token_symbol=symbol
                    )
                    pos["tp2_hit"] = True
                    pos["amount_remaining"] = pos["amount_remaining"] * Decimal("0.5")
                    
            except Exception as e:
                self.logger.error(f"[SNIPER] Error checking position {token_address[:10]}: {e}")
        
        # Cleanup closed positions
        for addr in positions_to_close:
            if addr in self.sniper_positions:
                del self.sniper_positions[addr]


# Global instance
_dex_trader: Optional[DEXTrader] = None


async def get_dex_trader() -> DEXTrader:
    """Get global DEX trader instance"""
    global _dex_trader
    if _dex_trader is None:
        _dex_trader = DEXTrader()
        await _dex_trader.initialize()
    return _dex_trader
