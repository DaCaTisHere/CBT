"""
Telegram Bot - Notifications and Alerts

Sends real-time notifications for:
- New trades executed
- Daily PnL reports
- Error alerts
- Momentum signals
- Safety mode changes
- Grid regime changes

============================================================
  HOW TO SET UP TELEGRAM NOTIFICATIONS
============================================================

  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the prompts to create your bot
  3. BotFather will give you a token like:
        123456789:ABCdefGHIjklMNOpqrsTUVwxyz
  4. To get your chat_id:
     - Search for @userinfobot on Telegram and start it
     - It will reply with your numeric chat_id
     - Alternatively, send a message to your bot, then visit:
       https://api.telegram.org/bot<TOKEN>/getUpdates
       and look for "chat":{"id": YOUR_CHAT_ID}
  5. Set these two environment variables on Railway:
        TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
        TELEGRAM_CHAT_ID=your_numeric_chat_id

  Once set, the bot will send real-time alerts for trades,
  mode switches, regime changes, and critical errors.
============================================================
"""

import asyncio
import time
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
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
    
    # Rate limiting: max 1 message per 3 seconds to avoid Telegram flood limits
    _RATE_LIMIT_SECONDS = 3.0

    def __init__(self, token: str = None, chat_id: str = None):
        self.logger = logger
        self.token = token or getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        self.chat_id = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', None)

        self.is_enabled = bool(self.token and self.chat_id)
        self.session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.messages_sent = 0
        self.errors = 0

        # Rate limiting state
        self._last_send_time: float = 0.0
        self._send_lock: Optional[asyncio.Lock] = None  # Lazy-init inside async context

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
        
        if not self.session:
            self.logger.warning("[TELEGRAM] Session not initialized")
            return False

        # Rate limiting — avoid Telegram flood ban (429)
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        async with self._send_lock:
            now = time.monotonic()
            elapsed = now - self._last_send_time
            if elapsed < self._RATE_LIMIT_SECONDS:
                await asyncio.sleep(self._RATE_LIMIT_SECONDS - elapsed)
            self._last_send_time = time.monotonic()

        try:
            url = f"{self.API_BASE}{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text[:4096],  # Telegram max message length
                "parse_mode": parse_mode,
                "disable_notification": silent,
            }

            async with self.session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    self.messages_sent += 1
                    return True
                elif response.status == 429:
                    retry_after = 5
                    try:
                        data = await response.json()
                        retry_after = data.get("parameters", {}).get("retry_after", 5)
                    except Exception:
                        pass
                    self.logger.warning(f"[TELEGRAM] Rate limited — retry in {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return False
                else:
                    error = await response.text()
                    self.logger.error(f"[TELEGRAM] Send failed ({response.status}): {error[:200]}")
                    self.errors += 1
                    return False

        except Exception as e:
            self.logger.error(f"[TELEGRAM] Error: {e}")
            self.errors += 1
            return False
    
    # ==================== NOTIFICATIONS (FR) ====================
    
    async def notify_trade_opened(self, symbol: str, side: str, price: float,
                                   amount: float, reason: str = ""):
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>{side.upper()} {symbol}</b>\n\n"
            f"💰 Montant: ${amount:.2f}\n"
            f"📊 Prix: ${price:.8f}\n"
            f"📝 Raison: {reason}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)

    async def notify_trade_closed(self, symbol: str, entry_price: float,
                                   exit_price: float, pnl: float,
                                   pnl_pct: float, reason: str = ""):
        emoji = "✅" if pnl >= 0 else "❌"
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>CLOSE {symbol}</b>\n\n"
            f"Entry: ${entry_price:.8f}\n"
            f"Exit: ${exit_price:.8f}\n"
            f"{pnl_emoji} P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)\n"
            f"📝 {reason}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)
    
    async def notify_momentum_signal(self, symbol: str, signal_type: str,
                                      change_pct: float, volume: float, score: float):
        msg = (
            f"⚡ <b>Signal Momentum: {symbol}</b>\n\n"
            f"Type: {signal_type}\n"
            f"24h: {change_pct:+.1f}% | Vol: ${volume/1e6:.1f}M\n"
            f"Score: {score:.0f}/100\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)

    async def notify_listing_detected(self, symbol: str, exchange: str, title: str):
        msg = (
            f"🆕 <b>Nouveau listing detecte</b>\n\n"
            f"Token: {symbol}\n"
            f"Exchange: {exchange}\n"
            f"Info: {title}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)
    
    async def send_daily_report(self, portfolio_value: float, daily_pnl: float,
                                daily_pnl_pct: float, total_pnl: float,
                                total_pnl_pct: float, trades_today: int,
                                win_rate: float, open_positions: int):
        emoji = "📈" if daily_pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>Rapport du jour</b>\n\n"
            f"💼 Portfolio: ${portfolio_value:.2f}\n"
            f"Jour: ${daily_pnl:+.2f} ({daily_pnl_pct:+.1f}%)\n"
            f"Total: ${total_pnl:+.2f} ({total_pnl_pct:+.1f}%)\n\n"
            f"Trades: {trades_today} | WR: {win_rate:.1f}%\n"
            f"Positions: {open_positions}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)
    
    async def send_position_update(self, positions: List[Dict[str, Any]]):
        if not positions:
            return
        lines = ["📋 <b>Positions ouvertes</b>\n"]
        for p in positions[:10]:
            pnl = p.get("pnl_pct", 0)
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"{emoji} {p.get('symbol', '?')}: {pnl:+.1f}% | ${p.get('value', 0):.2f}")
        lines.append(f"\n<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>")
        await self.send_message("\n".join(lines), silent=True)

    async def notify_mode_change(self, old_mode: str, new_mode: str, reason: str = ""):
        if new_mode.upper() == "REAL":
            message = (
                f"🚀🚀🚀 <b>BOT PRET POUR LE TRADING REEL !</b>\n\n"
                f"Le bot a termine sa phase de simulation avec succes.\n"
                f"Il est maintenant en mode <b>REEL</b>.\n\n"
                f"<b>Raison:</b> {reason or 'Criteres de simulation atteints'}\n\n"
                f"⚠️ Assure-toi d'avoir approvisionne le wallet avec des fonds.\n\n"
                f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
            )
        else:
            message = (
                f"⚠️ <b>Retour en SIMULATION</b>\n\n"
                f"Mode: {old_mode} → {new_mode}\n"
                f"Raison: {reason or 'Criteres non remplis'}\n\n"
                f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
            )
        await self.send_message(message, silent=False)

    async def notify_emergency_stop(self, reason: str):
        msg = (
            f"🚨🚨 <b>ARRET D'URGENCE</b>\n\n"
            f"Le bot a ete arrete automatiquement.\n"
            f"<b>Raison:</b> {reason}\n\n"
            f"Le bot repassera en simulation au prochain cycle.\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=False)

    async def notify_emergency_unlock(self):
        msg = (
            f"🔓 <b>Arret d'urgence leve</b>\n\n"
            f"Nouveau jour, le bot reprend en mode simulation.\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)

    async def notify_watchlist_add(self, symbol: str, change_pct: float, liquidity: float, score: float):
        msg = (
            f"👁️ <b>Watchlist: {symbol}</b>\n\n"
            f"24h: {change_pct:+.1f}% | Liq: ${liquidity:,.0f}\n"
            f"Score: {score:.0f}/100\n"
            f"En attente de confirmation momentum...\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)

    async def notify_ai_block(self, symbol: str, reason: str, change_pct: float):
        msg = (
            f"🤖❌ <b>AI Block: {symbol}</b>\n\n"
            f"Momentum: {change_pct:+.1f}% mais bloque par l'IA\n"
            f"Raison: {reason}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)

    async def notify_regime_change(self, pair: str, old_regime: str, new_regime: str, price: float):
        regime_emojis = {"bull": "🐂", "bull_volatile": "🐂⚡", "range": "↔️", "bear": "🐻"}
        emoji = regime_emojis.get(new_regime, "📊")
        msg = (
            f"{emoji} <b>Regime: {pair}</b>\n\n"
            f"{old_regime.upper()} → <b>{new_regime.upper()}</b>\n"
            f"Prix: ${price:,.2f}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)

    async def alert_error(self, error_type: str, message: str):
        msg = (
            f"⚠️ <b>Erreur: {error_type}</b>\n\n"
            f"{message}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)
    
    async def alert_critical(self, message: str):
        msg = (
            f"🚨 <b>CRITIQUE</b>\n\n"
            f"{message}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=False)

    async def notify_bot_started(self):
        msg = (
            f"🤖 <b>Cryptobot demarre — Association Netero</b>\n\n"
            f"Le bot est en ligne. 100% des profits vont à l'Association Netero.\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)

    async def notify_bot_stopped(self, reason: str = "Manual"):
        msg = (
            f"🛑 <b>Cryptobot arrete</b>\n\n"
            f"Raison: {reason}\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg)

    # ==================== HUMANITAIRE ====================

    async def notify_charity_milestone(self, milestone_usd: float, total_usd: float, is_simulation: bool = False):
        """Notifie qu'un jalon de profits réels est atteint pour l'Association Netero."""
        msg = (
            f"🎉 <b>JALON ATTEINT — Association Netero</b>\n\n"
            f"Le bot a généré <b>${milestone_usd:.0f}</b> de profits réels !\n\n"
            f"💰 Total cumulé : <b>${total_usd:.2f}</b>\n\n"
            f"🌍 Ces profits vont directement dans le wallet de l'Association Netero.\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=False)

    async def notify_charity_daily(self, daily_profit: float, total_sim: float,
                                    total_real: float, is_simulation: bool = True):
        """Rapport quotidien pour l'Association Netero."""
        mode = "simulation" if is_simulation else "REEL"
        emoji = "📊" if is_simulation else "💰"
        msg = (
            f"{emoji} <b>Rapport quotidien — Association Netero</b> <i>({mode})</i>\n\n"
            f"Profit du jour : <b>${daily_profit:+.4f}</b>\n\n"
            f"📈 Total simulation : <b>${total_sim:.4f}</b>\n"
            f"💰 Total réel : <b>${total_real:.4f}</b>\n\n"
            f"<i>100% des profits → Association Netero</i>\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=True)

    async def notify_mode_switch_to_real_charity(self, sim_profit_total: float):
        """Message spécial quand le bot passe en mode réel."""
        msg = (
            f"🚀 <b>PASSAGE EN MODE REEL — Association Netero</b>\n\n"
            f"Le bot a validé sa stratégie en simulation.\n"
            f"Profits simulés accumulés : <b>${sim_profit_total:.4f}</b>\n\n"
            f"Maintenant en mode <b>REEL</b> — chaque profit ira\n"
            f"directement dans le wallet de l'Association Netero.\n\n"
            f"<i>{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</i>"
        )
        await self.send_message(msg, silent=False)
    
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

