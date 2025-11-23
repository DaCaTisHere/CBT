"""
Wallet Manager - Multi-chain wallet operations
"""

from decimal import Decimal
from typing import Optional, Dict
from web3 import Web3
from eth_account import Account

from src.core.config import settings
from src.utils.logger import get_logger
from src.utils.helpers import wei_to_eth, eth_to_wei


logger = get_logger(__name__)


class WalletManager:
    """
    Multi-chain wallet management
    """
    
    def __init__(self):
        """Initialize wallet manager"""
        self.logger = logger
        
        # Ethereum wallet
        self.private_key = settings.WALLET_PRIVATE_KEY
        self.account = Account.from_key(self.private_key)
        self.address = self.account.address
        
        # Web3 connections
        self.w3_eth: Optional[Web3] = None
        self.w3_bsc: Optional[Web3] = None
        
        self.logger.info(f"[WALLET] Wallet Manager initialized")
        self.logger.info(f"   Address: {self.address}")
    
    async def initialize(self):
        """Initialize wallet connections"""
        try:
            # Ethereum
            rpc_url = settings.ETHEREUM_TESTNET_RPC_URL if settings.USE_TESTNET else settings.ETHEREUM_RPC_URL
            self.w3_eth = Web3(Web3.HTTPProvider(rpc_url))
            
            if not self.w3_eth.is_connected():
                raise ConnectionError("Failed to connect to Ethereum RPC")
            
            eth_balance = await self.get_eth_balance()
            self.logger.info(f"[OK] Ethereum connected | Balance: {eth_balance} ETH")
            
            # BSC
            rpc_url = settings.BSC_TESTNET_RPC_URL if settings.USE_TESTNET else settings.BSC_RPC_URL
            self.w3_bsc = Web3(Web3.HTTPProvider(rpc_url))
            
            if self.w3_bsc.is_connected():
                bnb_balance = await self.get_bnb_balance()
                self.logger.info(f"[OK] BSC connected | Balance: {bnb_balance} BNB")
            
        except Exception as e:
            self.logger.error(f"Wallet initialization error: {e}")
            raise
    
    async def get_eth_balance(self) -> Decimal:
        """Get ETH balance"""
        if not self.w3_eth:
            return Decimal("0")
        
        balance_wei = self.w3_eth.eth.get_balance(self.address)
        return wei_to_eth(balance_wei)
    
    async def get_bnb_balance(self) -> Decimal:
        """Get BNB balance"""
        if not self.w3_bsc:
            return Decimal("0")
        
        balance_wei = self.w3_bsc.eth.get_balance(self.address)
        return wei_to_eth(balance_wei)
    
    async def get_token_balance(self, token_address: str, chain: str = "ethereum") -> Decimal:
        """Get ERC20 token balance"""
        w3 = self.w3_eth if chain == "ethereum" else self.w3_bsc
        
        if not w3:
            return Decimal("0")
        
        # ERC20 ABI (balanceOf function)
        abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            }
        ]
        
        contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=abi)
        balance = contract.functions.balanceOf(self.address).call()
        
        # Assuming 18 decimals (most ERC20 tokens)
        return Decimal(balance) / Decimal(10**18)
    
    async def get_all_balances(self) -> Dict[str, Decimal]:
        """Get all wallet balances"""
        balances = {}
        
        # ETH
        balances["ETH"] = await self.get_eth_balance()
        
        # BNB
        balances["BNB"] = await self.get_bnb_balance()
        
        return balances
    
    def sign_transaction(self, transaction: Dict) -> str:
        """Sign a transaction"""
        signed = self.account.sign_transaction(transaction)
        return signed.rawTransaction.hex()

