"""
Mempool Monitor for Sniper Bot

Monitors Ethereum mempool for new token pair creations.
Detects PairCreated events from Uniswap V2/V3 and other DEXes.
"""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from decimal import Decimal
from web3 import Web3
from web3.types import FilterParams
from eth_utils import to_checksum_address
import json

from src.core.config import settings
from src.utils.logger import get_logger


logger = get_logger(__name__)


class MempoolMonitor:
    """
    Monitors mempool and blockchain events for new token pairs
    """
    
    # Uniswap V2 Factory address (mainnet)
    UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    
    # Uniswap V3 Factory address (mainnet)
    UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    
    # PancakeSwap Factory (BSC)
    PANCAKESWAP_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    
    # PairCreated event signature (Uniswap V2)
    PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    
    # PoolCreated event signature (Uniswap V3)
    POOL_CREATED_TOPIC = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
    
    # Uniswap V2 Factory ABI (minimal - just PairCreated event)
    FACTORY_ABI = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "token0", "type": "address"},
                {"indexed": True, "name": "token1", "type": "address"},
                {"indexed": False, "name": "pair", "type": "address"},
                {"indexed": False, "name": "", "type": "uint256"}
            ],
            "name": "PairCreated",
            "type": "event"
        }
    ]
    
    def __init__(self, w3: Web3, chain: str = "ethereum"):
        """
        Initialize mempool monitor
        
        Args:
            w3: Web3 instance
            chain: Blockchain to monitor (ethereum, bsc, etc.)
        """
        self.w3 = w3
        self.chain = chain
        self.logger = logger
        
        # Event callbacks
        self.pair_created_callbacks: List[Callable] = []
        
        # Tracking
        self.pairs_detected = 0
        self.is_running = False
        
        # Select factory based on chain
        if chain == "bsc":
            self.factory_address = self.PANCAKESWAP_FACTORY
        else:
            self.factory_address = self.UNISWAP_V2_FACTORY
        
        self.logger.info(f"[MEMPOOL] Monitor initialized for {chain}")
        self.logger.info(f"   Factory: {self.factory_address}")
    
    def on_pair_created(self, callback: Callable):
        """
        Register callback for PairCreated events
        
        Callback signature: async def callback(token0, token1, pair_address)
        """
        self.pair_created_callbacks.append(callback)
        self.logger.info(f"   Registered pair creation callback")
    
    async def start(self):
        """
        Start monitoring for new pairs
        """
        self.is_running = True
        self.logger.info("[RUN]  Mempool monitor started")
        
        try:
            # Start event monitoring
            await self._monitor_events()
            
        except asyncio.CancelledError:
            self.logger.info("Mempool monitor cancelled")
        except Exception as e:
            self.logger.error(f"Mempool monitor error: {e}")
        finally:
            await self.stop()
    
    async def _monitor_events(self):
        """
        Monitor blockchain events for new pair creations
        
        Uses event filters to detect PairCreated events in real-time
        """
        # Create event filter for PairCreated
        factory_contract = self.w3.eth.contract(
            address=to_checksum_address(self.factory_address),
            abi=self.FACTORY_ABI
        )
        
        # Create filter for PairCreated events
        event_filter = factory_contract.events.PairCreated.create_filter(fromBlock='latest')
        
        self.logger.info(f"   📡 Listening for PairCreated events...")
        
        while self.is_running:
            try:
                # Get new events
                events = event_filter.get_new_entries()
                
                for event in events:
                    await self._handle_pair_created_event(event)
                
                # Small delay to avoid hammering the node
                await asyncio.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Event monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _handle_pair_created_event(self, event: Dict[str, Any]):
        """
        Handle a PairCreated event
        
        Args:
            event: Event data from Web3
        """
        try:
            # Extract event data
            args = event['args']
            token0 = args['token0']
            token1 = args['token1']
            pair_address = args['pair']
            
            self.pairs_detected += 1
            
            self.logger.info(f"🔔 New pair detected #{self.pairs_detected}")
            self.logger.info(f"   Pair: {pair_address[:10]}...")
            self.logger.info(f"   Token0: {token0[:10]}...")
            self.logger.info(f"   Token1: {token1[:10]}...")
            
            # Determine which token is the new one (not WETH/USDT/etc.)
            new_token = await self._identify_new_token(token0, token1)
            
            if new_token:
                self.logger.info(f"   ✨ New token: {new_token[:10]}...")
                
                # Call registered callbacks
                for callback in self.pair_created_callbacks:
                    try:
                        await callback(new_token, pair_address)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
            else:
                self.logger.info(f"   ⚠️  Could not identify new token (might be stablecoin pair)")
            
        except Exception as e:
            self.logger.error(f"Error handling PairCreated event: {e}")
    
    async def _identify_new_token(self, token0: str, token1: str) -> Optional[str]:
        """
        Identify which token is the new one in a pair
        
        The new token is the one that's not a known base token (WETH, USDT, USDC, DAI)
        
        Args:
            token0: First token address
            token1: Second token address
        
        Returns:
            Address of the new token, or None if both are known
        """
        # Known base tokens (checksummed)
        KNOWN_BASES = {
            # Ethereum mainnet
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
            
            # BSC
            "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB (BSC)
            "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",  # BUSD (BSC)
            "0x55d398326f99059fF775485246999027B3197955",  # USDT (BSC)
        }
        
        token0_checksum = to_checksum_address(token0)
        token1_checksum = to_checksum_address(token1)
        
        # Check which token is new
        token0_is_known = token0_checksum in KNOWN_BASES
        token1_is_known = token1_checksum in KNOWN_BASES
        
        if token0_is_known and not token1_is_known:
            return token1_checksum
        elif token1_is_known and not token0_is_known:
            return token0_checksum
        elif not token0_is_known and not token1_is_known:
            # Both are new? Return token1 by default
            return token1_checksum
        else:
            # Both are known base tokens (unusual)
            return None
    
    async def stop(self):
        """Stop monitoring"""
        self.is_running = False
        self.logger.info("[STOP]  Mempool monitor stopped")
        self.logger.info(f"   Total pairs detected: {self.pairs_detected}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics"""
        return {
            "is_running": self.is_running,
            "pairs_detected": self.pairs_detected,
            "chain": self.chain,
            "factory": self.factory_address,
        }


class MempoolMonitorV3(MempoolMonitor):
    """
    Mempool monitor specialized for Uniswap V3
    
    V3 uses PoolCreated instead of PairCreated
    """
    
    # Uniswap V3 Factory ABI (minimal)
    FACTORY_ABI_V3 = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "token0", "type": "address"},
                {"indexed": True, "name": "token1", "type": "address"},
                {"indexed": True, "name": "fee", "type": "uint24"},
                {"indexed": False, "name": "tickSpacing", "type": "int24"},
                {"indexed": False, "name": "pool", "type": "address"}
            ],
            "name": "PoolCreated",
            "type": "event"
        }
    ]
    
    def __init__(self, w3: Web3, chain: str = "ethereum"):
        """Initialize V3 monitor"""
        super().__init__(w3, chain)
        self.factory_address = self.UNISWAP_V3_FACTORY
        self.logger.info(f"[MEMPOOL] V3 monitor initialized")
    
    async def _monitor_events(self):
        """Monitor V3 PoolCreated events"""
        factory_contract = self.w3.eth.contract(
            address=to_checksum_address(self.factory_address),
            abi=self.FACTORY_ABI_V3
        )
        
        # Create filter for PoolCreated events
        event_filter = factory_contract.events.PoolCreated.create_filter(fromBlock='latest')
        
        self.logger.info(f"   📡 Listening for PoolCreated events (V3)...")
        
        while self.is_running:
            try:
                events = event_filter.get_new_entries()
                
                for event in events:
                    # Extract pool data
                    args = event['args']
                    token0 = args['token0']
                    token1 = args['token1']
                    pool_address = args['pool']
                    fee = args['fee']
                    
                    self.pairs_detected += 1
                    
                    self.logger.info(f"🔔 New V3 pool detected #{self.pairs_detected}")
                    self.logger.info(f"   Pool: {pool_address[:10]}... (fee: {fee/10000}%)")
                    
                    # Identify new token and notify
                    new_token = await self._identify_new_token(token0, token1)
                    if new_token:
                        for callback in self.pair_created_callbacks:
                            try:
                                await callback(new_token, pool_address)
                            except Exception as e:
                                self.logger.error(f"Callback error: {e}")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                self.logger.error(f"V3 event monitoring error: {e}")
                await asyncio.sleep(5)
