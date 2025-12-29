"""
Telegram Bot - Notifications and Alerts

Sends real-time notifications for:
- New trades executed
- Daily PnL reports
- Error alerts
- Momentum signals
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TelegramMessage:
    """A Telegram message"""
    text: str
    parse_mode: str = "HTML"
    disable_notification: bool = False


class TelegramBot:
    """
    Telegram notification bot
    
    Features:
    - Trade notifications
    - Daily reports
    - Error alerts
    - Position updates
    """
    
    API_BASE = "https://api.telegram.org/bot"
    
    def __init__(self, token: str = None, chat_id: str = None):
        self.logger = logger
        self.token = token or getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        self.chat_id = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', None)
        
        self.is_enabled = bool(self.token and self.chat_id)
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.messages_sent = 0
        self.errors = 0
        
        if self.is_enabled:
            self.logger.info("[TELEGRAM] Bot initialized")
        else:
            self.logger.warning("[TELEGRAM] Bot disabled (no token/chat_id)")
    
    async def initialize(self):
        """Initialize the bot"""
        if not self.is_enabled:
            return
        
        self.session = aiohttp.ClientSession()
        
        # Test connection
        try:
            url = f"{self.API_BASE}{self.token}/getMe"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    bot_name = data.get('result', {}).get('username', 'Unknown')
                    self.logger.info(f"[TELEGRAM] Connected as @{bot_name}")
                else:
                    self.logger.error(f"[TELEGRAM] Connection failed: {response.status}")
                    self.is_enabled = False
        except Exception as e:
            self.logger.error(f"[TELEGRAM] Init error: {e}")
            self.is_enabled = False
    
    async def send_message(self, text: str, parse_mode: str = "HTML", silent: bool = False) -> bool:
        """
        Send a message to the configured chat
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
            silent: If True, sends without notification sound
            
        Returns:
            True if sent successfully
        """
        if not self.is_enabled:
            self.logger.debug(f"[TELEGRAM] Would send: {text[:50]}...")
            return False
        
        try:
            url = f"{self.API_BASE}{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": silent
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    self.messages_sent += 1
                    return True
                else:
                    error = await response.text()
                    self.logger.error(f"[TELEGRAM] Send failed: {error}")
                    self.errors += 1
                    return False
                    
        except Exception as e:
            self.logger.error(f"[TELEGRAM] Error: {e}")
            self.errors += 1
            return False
    
    # ==================== TRADE NOTIFICATIONS ====================
    
    async def notify_trade_opened(
        self,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        reason: str = ""
    ):
        """Notify when a trade is opened"""
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        
        message = f"""
{emoji} <b>TRADE OPENED</b>

<b>Symbol:</b> {symbol}
<b>Side:</b> {side.upper()}
<b>Price:</b> ${price:.6f}
<b>Amount:</b> ${amount:.2f}
<b>Reason:</b> {reason}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip())
    
    async def notify_trade_closed(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str = ""
    ):
        """Notify when a trade is closed"""
        emoji = "✅" if pnl >= 0 else "❌"
        pnl_sign = "+" if pnl >= 0 else ""
        
        message = f"""
{emoji} <b>TRADE CLOSED</b>

<b>Symbol:</b> {symbol}
<b>Entry:</b> ${entry_price:.6f}
<b>Exit:</b> ${exit_price:.6f}
<b>PnL:</b> {pnl_sign}${pnl:.2f} ({pnl_sign}{pnl_pct:.2f}%)
<b>Reason:</b> {reason}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip())
    
    # ==================== SIGNAL NOTIFICATIONS ====================
    
    async def notify_momentum_signal(
        self,
        symbol: str,
        signal_type: str,
        change_pct: float,
        volume: float,
        score: float
    ):
        """Notify about a momentum signal"""
        message = f"""
📊 <b>MOMENTUM SIGNAL</b>

<b>Symbol:</b> {symbol}
<b>Type:</b> {signal_type}
<b>Change:</b> +{change_pct:.2f}%
<b>Volume:</b> ${volume:,.0f}
<b>Score:</b> {score:.0f}/100

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip(), silent=True)
    
    async def notify_listing_detected(
        self,
        symbol: str,
        exchange: str,
        title: str
    ):
        """Notify about a new listing detection"""
        message = f"""
🔔 <b>NEW LISTING DETECTED</b>

<b>Symbol:</b> {symbol}
<b>Exchange:</b> {exchange}
<b>Title:</b> {title[:100]}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip())
    
    # ==================== REPORTS ====================
    
    async def send_daily_report(
        self,
        portfolio_value: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        total_pnl: float,
        total_pnl_pct: float,
        trades_today: int,
        win_rate: float,
        open_positions: int
    ):
        """Send daily performance report"""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        daily_sign = "+" if daily_pnl >= 0 else ""
        total_sign = "+" if total_pnl >= 0 else ""
        
        message = f"""
{pnl_emoji} <b>DAILY REPORT</b>

💰 <b>Portfolio:</b> ${portfolio_value:,.2f}

📊 <b>Today:</b>
   PnL: {daily_sign}${daily_pnl:.2f} ({daily_sign}{daily_pnl_pct:.2f}%)
   Trades: {trades_today}

📈 <b>Total:</b>
   PnL: {total_sign}${total_pnl:.2f} ({total_sign}{total_pnl_pct:.2f}%)
   Win Rate: {win_rate:.1f}%

📍 <b>Open Positions:</b> {open_positions}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip())
    
    async def send_position_update(
        self,
        positions: List[Dict[str, Any]]
    ):
        """Send current positions summary"""
        if not positions:
            message = "📍 <b>POSITIONS</b>\n\nNo open positions"
        else:
            pos_lines = []
            for pos in positions[:10]:  # Max 10 positions
                symbol = pos.get('symbol', 'Unknown')
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)
                pnl_pct = ((current - entry) / entry * 100) if entry > 0 else 0
                emoji = "🟢" if pnl_pct >= 0 else "🔴"
                pos_lines.append(f"{emoji} {symbol}: ${current:.4f} ({pnl_pct:+.2f}%)")
            
            message = f"""
📍 <b>OPEN POSITIONS ({len(positions)})</b>

{chr(10).join(pos_lines)}

<i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>
"""
        
        await self.send_message(message.strip(), silent=True)
    
    # ==================== ALERTS ====================
    
    async def alert_error(self, error_type: str, message: str):
        """Send error alert"""
        alert = f"""
⚠️ <b>ERROR ALERT</b>

<b>Type:</b> {error_type}
<b>Message:</b> {message}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(alert.strip())
    
    async def alert_critical(self, message: str):
        """Send critical alert (with notification sound)"""
        alert = f"""
🚨 <b>CRITICAL ALERT</b>

{message}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(alert.strip(), silent=False)
    
    async def notify_bot_started(self):
        """Notify that the bot has started"""
        message = """
🚀 <b>CRYPTOBOT STARTED</b>

The trading bot is now online and monitoring markets.

Mode: SIMULATION
Capital: $10,000 (virtual)

<i>Good luck!</i>
"""
        await self.send_message(message.strip())
    
    async def notify_bot_stopped(self, reason: str = "Manual"):
        """Notify that the bot has stopped"""
        message = f"""
🛑 <b>CRYPTOBOT STOPPED</b>

Reason: {reason}

<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>
"""
        await self.send_message(message.strip())
    
    # ==================== CLEANUP ====================
    
    async def close(self):
        """Close the bot session"""
        if self.session:
            await self.session.close()
        self.logger.info(f"[TELEGRAM] Closed. Messages sent: {self.messages_sent}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        return {
            "is_enabled": self.is_enabled,
            "messages_sent": self.messages_sent,
            "errors": self.errors
        }


# Global instance
_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    """Get or create global Telegram bot instance"""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBot()
    return _telegram_bot


async def init_telegram() -> TelegramBot:
    """Initialize global Telegram bot"""
    bot = get_telegram_bot()
    await bot.initialize()
    return bot

