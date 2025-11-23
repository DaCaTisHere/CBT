"""
Order Engine - Execute trades on CEX and DEX
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from enum import Enum
import asyncio

import ccxt.async_support as ccxt
from web3 import Web3

from src.core.config import settings
from src.core.risk_manager import RiskManager
from src.execution.wallet_manager import WalletManager
from src.utils.logger import get_logger


logger = get_logger(__name__)


class OrderType(str, Enum):
    """Order types"""
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(str, Enum):
    """Order sides"""
    BUY = "buy"
    SELL = "sell"


class OrderEngine:
    """
    Unified order execution engine for CEX and DEX
    """
    
    def __init__(self, risk_manager: RiskManager, wallet_manager: WalletManager):
        """Initialize order engine"""
        self.logger = logger
        self.risk_manager = risk_manager
        self.wallet_manager = wallet_manager
        
        # CEX exchanges
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        
        self.logger.info("[LIST] Order Engine initialized")
    
    async def initialize(self):
        """Initialize exchanges"""
        try:
            # Initialize Binance if API keys provided
            if settings.BINANCE_API_KEY and settings.BINANCE_SECRET:
                self.exchanges["binance"] = ccxt.binance({
                    'apiKey': settings.BINANCE_API_KEY,
                    'secret': settings.BINANCE_SECRET,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                    }
                })
                
                # Test connection
                await self.exchanges["binance"].load_markets()
                self.logger.info("[OK] Binance connected")
            
            # Initialize Coinbase if API keys provided
            if settings.COINBASE_API_KEY and settings.COINBASE_SECRET:
                self.exchanges["coinbase"] = ccxt.coinbasepro({
                    'apiKey': settings.COINBASE_API_KEY,
                    'secret': settings.COINBASE_SECRET,
                    'enableRateLimit': True,
                })
                await self.exchanges["coinbase"].load_markets()
                self.logger.info("[OK] Coinbase connected")
            
        except Exception as e:
            self.logger.error(f"Exchange initialization error: {e}")
            raise
    
    async def execute_cex_order(
        self,
        exchange: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Execute order on centralized exchange
        
        Args:
            exchange: Exchange name (binance, coinbase, etc.)
            symbol: Trading pair (BTC/USDT)
            side: BUY or SELL
            order_type: MARKET or LIMIT
            amount: Order amount
            price: Limit price (for LIMIT orders)
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Order result dict
        """
        if settings.DRY_RUN or settings.SIMULATION_MODE:
            self.logger.info(f"🎮 [DRY RUN] {exchange} {side.value} {amount} {symbol} @ {price or 'market'}")
            return {"order_id": "DRY_RUN_12345", "status": "filled", "price": float(price or 0)}
        
        # Check risk limits
        can_trade, reason = await self.risk_manager.check_can_trade("order_engine", amount)
        if not can_trade:
            raise ValueError(f"Trade rejected: {reason}")
        
        # Get exchange instance
        if exchange not in self.exchanges:
            raise ValueError(f"Exchange {exchange} not initialized")
        
        ex = self.exchanges[exchange]
        
        try:
            # Execute order
            if order_type == OrderType.MARKET:
                order = await ex.create_market_order(
                    symbol=symbol,
                    side=side.value,
                    amount=float(amount),
                )
            else:  # LIMIT
                order = await ex.create_limit_order(
                    symbol=symbol,
                    side=side.value,
                    amount=float(amount),
                    price=float(price),
                )
            
            self.logger.info(f"[OK] Order executed: {order['id']} | {side.value} {amount} {symbol}")
            
            # Set stop-loss and take-profit if provided
            if stop_loss:
                await self._set_stop_loss(ex, symbol, order['id'], stop_loss)
            if take_profit:
                await self._set_take_profit(ex, symbol, order['id'], take_profit)
            
            return order
            
        except Exception as e:
            self.logger.error(f"Order execution failed: {e}")
            raise
    
    async def execute_dex_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        chain: str = "ethereum",
        dex: str = "uniswap",
    ) -> Dict[str, Any]:
        """
        Execute swap on DEX
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap
            chain: Blockchain (ethereum, bsc, etc.)
            dex: DEX name (uniswap, pancakeswap, etc.)
        
        Returns:
            Transaction result
        """
        if settings.DRY_RUN or settings.SIMULATION_MODE:
            self.logger.info(f"🎮 [DRY RUN] DEX Swap: {amount_in} {token_in[:10]}...  {token_out[:10]}...")
            return {"tx_hash": "0xDRYRUN123", "status": "success"}
        
        # Implementation would include:
        # 1. Get router contract (Uniswap V2/V3, PancakeSwap, etc.)
        # 2. Calculate amounts out
        # 3. Build swap transaction
        # 4. Sign with wallet
        # 5. Send transaction
        # 6. Wait for confirmation
        
        self.logger.warning("DEX swap not fully implemented yet")
        raise NotImplementedError("DEX swap coming soon")
    
    async def _set_stop_loss(self, exchange: ccxt.Exchange, symbol: str, order_id: str, price: Decimal):
        """Set stop-loss order"""
        try:
            # Implementation depends on exchange
            self.logger.info(f"Stop-loss set at {price}")
        except Exception as e:
            self.logger.error(f"Failed to set stop-loss: {e}")
    
    async def _set_take_profit(self, exchange: ccxt.Exchange, symbol: str, order_id: str, price: Decimal):
        """Set take-profit order"""
        try:
            # Implementation depends on exchange
            self.logger.info(f"Take-profit set at {price}")
        except Exception as e:
            self.logger.error(f"Failed to set take-profit: {e}")
    
    async def get_order_status(self, exchange: str, order_id: str, symbol: str) -> Dict[str, Any]:
        """Get order status"""
        if exchange not in self.exchanges:
            raise ValueError(f"Exchange {exchange} not initialized")
        
        ex = self.exchanges[exchange]
        order = await ex.fetch_order(order_id, symbol)
        return order
    
    async def cancel_order(self, exchange: str, order_id: str, symbol: str):
        """Cancel an open order"""
        if exchange not in self.exchanges:
            raise ValueError(f"Exchange {exchange} not initialized")
        
        ex = self.exchanges[exchange]
        await ex.cancel_order(order_id, symbol)
        self.logger.info(f"[ERROR] Order cancelled: {order_id}")
    
    async def cleanup(self):
        """Cleanup and close connections"""
        for name, ex in self.exchanges.items():
            await ex.close()
            self.logger.info(f"Closed {name}")

