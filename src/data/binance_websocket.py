"""
Binance WebSocket - Real-time price data

Provides instant price updates via WebSocket instead of polling.
Latency: <100ms vs 5000ms with REST API
"""

import asyncio
import json
import aiohttp
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BinanceWebSocket:
    """
    Binance WebSocket client for real-time price data
    
    Features:
    - Multiple symbol subscriptions
    - Auto-reconnect on disconnect
    - Price callbacks for trading logic
    - Ticker and trade streams
    """
    
    WS_BASE_URL = "wss://stream.binance.com:9443/ws"
    WS_COMBINED_URL = "wss://stream.binance.com:9443/stream?streams="
    
    def __init__(self):
        self.logger = logger
        self.is_running = False
        self.ws = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Price cache
        self.prices: Dict[str, float] = {}
        self.last_update: Dict[str, datetime] = {}
        
        # Callbacks
        self.price_callbacks: List[Callable] = []
        self.trade_callbacks: List[Callable] = []
        
        # Subscribed symbols
        self.subscribed_symbols: List[str] = []
        
        # Stats
        self.messages_received = 0
        self.reconnect_count = 0
        
        self.logger.info("[WS] Binance WebSocket initialized")
    
    def on_price_update(self, callback: Callable):
        """Register callback for price updates"""
        self.price_callbacks.append(callback)
    
    def on_trade(self, callback: Callable):
        """Register callback for trade events"""
        self.trade_callbacks.append(callback)
    
    async def connect(self, symbols: List[str] = None):
        """
        Connect to Binance WebSocket
        
        Args:
            symbols: List of symbols to subscribe (e.g., ["btcusdt", "ethusdt"])
        """
        if symbols:
            self.subscribed_symbols = [s.lower() for s in symbols]
        
        if not self.subscribed_symbols:
            # Default: top 50 trading pairs for broader coverage
            self.subscribed_symbols = [
                "btcusdt", "ethusdt", "bnbusdt", "solusdt", "xrpusdt",
                "dogeusdt", "adausdt", "avaxusdt", "dotusdt", "maticusdt",
                "linkusdt", "ltcusdt", "uniusdt", "atomusdt", "etcusdt",
                "xlmusdt", "nearusdt", "injusdt", "aptusdt", "suiusdt",
                "seiusdt", "tiausdt", "jupusdt", "wifusdt", "pepeusdt",
                "shibusdt", "flokiusdt", "bonkusdt", "fetusdt", "renderusdt",
                "arusdt", "filusdt", "grtusdt", "imxusdt", "opusdt",
                "arbusdt", "mkrusdt", "aaveusdt", "snxusdt", "crvusdt",
                "ldousdt", "rndrusdt", "enausdt", "stxusdt", "runeusdt",
                "kasusdt", "ordiusdt", "1000satsusdt", "wldusdt", "pythusdt"
            ]
        
        self.is_running = True
        self.session = aiohttp.ClientSession()
        
        await self._connect_websocket()
    
    async def _connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            # Build stream URL for multiple symbols
            streams = [f"{s}@ticker" for s in self.subscribed_symbols]
            url = self.WS_COMBINED_URL + "/".join(streams)
            
            self.logger.info(f"[WS] Connecting to Binance WebSocket...")
            self.logger.info(f"[WS] Subscribing to {len(self.subscribed_symbols)} symbols")
            
            async with self.session.ws_connect(url) as ws:
                self.ws = ws
                self.logger.info("[WS] ✅ Connected to Binance WebSocket")
                
                async for msg in ws:
                    if not self.is_running:
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        self.logger.error(f"[WS] Error: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        self.logger.warning("[WS] Connection closed")
                        break
            
            # Reconnect if still running
            if self.is_running:
                self.reconnect_count += 1
                self.logger.info(f"[WS] Reconnecting... (attempt {self.reconnect_count})")
                await asyncio.sleep(5)
                await self._connect_websocket()
                
        except Exception as e:
            self.logger.error(f"[WS] Connection error: {e}")
            if self.is_running:
                await asyncio.sleep(10)
                await self._connect_websocket()
    
    async def _handle_message(self, data: str):
        """Handle incoming WebSocket message"""
        try:
            message = json.loads(data)
            self.messages_received += 1
            
            # Combined stream format
            if "stream" in message and "data" in message:
                stream = message["stream"]
                ticker_data = message["data"]
                
                if "@ticker" in stream:
                    await self._handle_ticker(ticker_data)
            
        except Exception as e:
            self.logger.error(f"[WS] Message handling error: {e}")
    
    async def _handle_ticker(self, data: Dict[str, Any]):
        """Handle 24hr ticker data"""
        try:
            symbol = data.get("s", "").upper()  # Symbol
            price = float(data.get("c", 0))  # Last price
            change_pct = float(data.get("P", 0))  # 24h change %
            volume = float(data.get("q", 0))  # Quote volume (USDT)
            
            # Update price cache
            self.prices[symbol] = price
            self.last_update[symbol] = datetime.utcnow()
            
            # Build price update object
            price_update = {
                "symbol": symbol,
                "price": price,
                "change_24h_pct": change_pct,
                "volume_24h": volume,
                "timestamp": datetime.utcnow()
            }
            
            # Notify callbacks
            for callback in self.price_callbacks:
                try:
                    await callback(price_update)
                except Exception as e:
                    self.logger.error(f"[WS] Callback error: {e}")
            
        except Exception as e:
            self.logger.error(f"[WS] Ticker handling error: {e}")
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get cached price for symbol"""
        return self.prices.get(symbol.upper())
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices"""
        return self.prices.copy()
    
    async def subscribe(self, symbols: List[str]):
        """Subscribe to additional symbols"""
        new_symbols = [s.lower() for s in symbols if s.lower() not in self.subscribed_symbols]
        
        if new_symbols and self.ws:
            self.subscribed_symbols.extend(new_symbols)
            
            # Send subscription message
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [f"{s}@ticker" for s in new_symbols],
                "id": self.messages_received
            }
            
            await self.ws.send_str(json.dumps(subscribe_msg))
            self.logger.info(f"[WS] Subscribed to {len(new_symbols)} new symbols")
    
    async def stop(self):
        """Stop WebSocket connection"""
        self.is_running = False
        
        if self.ws:
            await self.ws.close()
        
        if self.session:
            await self.session.close()
        
        self.logger.info("[WS] WebSocket stopped")
        self.logger.info(f"[WS] Total messages received: {self.messages_received}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics"""
        return {
            "is_connected": self.is_running and self.ws is not None,
            "symbols_subscribed": len(self.subscribed_symbols),
            "messages_received": self.messages_received,
            "reconnect_count": self.reconnect_count,
            "prices_cached": len(self.prices)
        }


# Global instance
_ws_client: Optional[BinanceWebSocket] = None


def get_websocket() -> BinanceWebSocket:
    """Get or create global WebSocket instance"""
    global _ws_client
    if _ws_client is None:
        _ws_client = BinanceWebSocket()
    return _ws_client


async def start_websocket(symbols: List[str] = None) -> BinanceWebSocket:
    """Start global WebSocket client"""
    ws = get_websocket()
    asyncio.create_task(ws.connect(symbols))
    return ws

