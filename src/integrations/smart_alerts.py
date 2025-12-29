"""
Smart Alerts System - Alertes intelligentes multi-canal
Telegram, Email, Webhooks avec priorisation et rate limiting
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from collections import deque
import aiohttp

class SmartAlerts:
    """
    Système d'alertes intelligent qui:
    1. Détecte les événements critiques
    2. Priorise les alertes (critical > warning > info)
    3. Rate limiting (pas de spam)
    4. Multi-canal (Telegram, Email, Webhook)
    5. Escalation automatique
    """
    
    # Alert levels
    CRITICAL = 'critical'  # Problème grave, action immédiate requise
    WARNING = 'warning'    # Attention requise
    INFO = 'info'          # Information seulement
    
    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        email_config: Optional[Dict] = None
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Channels config
        self.telegram_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.webhook_url = webhook_url
        self.email_config = email_config
        
        # Rate limiting (éviter spam)
        self.alert_history: deque = deque(maxlen=1000)
        self.last_alert_time: Dict[str, datetime] = {}
        self.min_interval_seconds = {
            self.CRITICAL: 0,      # Pas de limite pour critical
            self.WARNING: 300,     # Max 1 warning / 5 min
            self.INFO: 600         # Max 1 info / 10 min
        }
        
        # Escalation (si plusieurs alertes critical)
        self.critical_count = 0
        self.escalation_threshold = 3  # 3 critical = escalation
        
        self.logger.info("🚨 Smart Alerts System initialized")
    
    async def send_alert(
        self,
        level: str,
        title: str,
        message: str,
        data: Optional[Dict] = None,
        force: bool = False
    ) -> bool:
        """
        Envoie une alerte intelligente
        
        Args:
            level: CRITICAL, WARNING, ou INFO
            title: Titre de l'alerte
            message: Message détaillé
            data: Données additionnelles (JSON)
            force: Bypass rate limiting
            
        Returns:
            True si envoyé, False si rate limited
        """
        # Check rate limiting
        if not force and not self._should_send(level, title):
            self.logger.debug(f"⏭️ Alert rate limited: {title}")
            return False
        
        # Record alert
        alert = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'title': title,
            'message': message,
            'data': data
        }
        self.alert_history.append(alert)
        self.last_alert_time[f"{level}:{title}"] = datetime.utcnow()
        
        # Escalation pour critical
        if level == self.CRITICAL:
            self.critical_count += 1
            if self.critical_count >= self.escalation_threshold:
                await self._escalate()
        
        # Send to all channels
        await self._send_telegram(level, title, message, data)
        await self._send_webhook(level, title, message, data)
        
        # Log
        emoji = self._get_emoji(level)
        self.logger.info(f"{emoji} Alert sent: [{level.upper()}] {title}")
        
        return True
    
    def _should_send(self, level: str, title: str) -> bool:
        """Vérifie si on peut envoyer (rate limiting)"""
        key = f"{level}:{title}"
        
        if key not in self.last_alert_time:
            return True
        
        last_time = self.last_alert_time[key]
        elapsed = (datetime.utcnow() - last_time).total_seconds()
        min_interval = self.min_interval_seconds.get(level, 600)
        
        return elapsed >= min_interval
    
    def _get_emoji(self, level: str) -> str:
        """Emoji selon niveau"""
        return {
            self.CRITICAL: '🚨',
            self.WARNING: '⚠️',
            self.INFO: 'ℹ️'
        }.get(level, '📢')
    
    async def _send_telegram(
        self,
        level: str,
        title: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """Envoie alerte sur Telegram"""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        try:
            emoji = self._get_emoji(level)
            text = f"{emoji} **{title}**\n\n{message}"
            
            if data:
                text += f"\n\n```json\n{str(data)[:500]}\n```"
            
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            async with aiohttp.ClientSession() as session:
                await session.post(
                    url,
                    json={
                        'chat_id': self.telegram_chat_id,
                        'text': text,
                        'parse_mode': 'Markdown'
                    }
                )
            
            self.logger.debug("✅ Telegram alert sent")
        
        except Exception as e:
            self.logger.error(f"❌ Telegram alert failed: {e}")
    
    async def _send_webhook(
        self,
        level: str,
        title: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """Envoie alerte sur Webhook (Discord, Slack, etc.)"""
        if not self.webhook_url:
            return
        
        try:
            payload = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'title': title,
                'message': message,
                'data': data
            }
            
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=payload)
            
            self.logger.debug("✅ Webhook alert sent")
        
        except Exception as e:
            self.logger.error(f"❌ Webhook alert failed: {e}")
    
    async def _escalate(self):
        """Escalation automatique si trop d'alertes critical"""
        self.logger.warning(
            f"🚨 ESCALATION: {self.critical_count} critical alerts in short time!"
        )
        
        await self.send_alert(
            level=self.CRITICAL,
            title='🚨 ESCALATION: Multiple Critical Alerts',
            message=f'{self.critical_count} critical alerts detected. Bot may need manual intervention.',
            force=True
        )
        
        # Reset counter
        self.critical_count = 0
    
    async def alert_performance_issue(
        self,
        win_rate: float,
        target_win_rate: float,
        trades_count: int
    ):
        """Alerte performance (win rate trop bas)"""
        if win_rate < target_win_rate * 0.8:  # -20% du target
            level = self.CRITICAL
        elif win_rate < target_win_rate * 0.9:  # -10% du target
            level = self.WARNING
        else:
            return  # Pas d'alerte
        
        await self.send_alert(
            level=level,
            title='📉 Performance Issue Detected',
            message=f'Win rate: {win_rate:.1f}% (target: {target_win_rate:.1f}%)\nTrades: {trades_count}',
            data={'win_rate': win_rate, 'target': target_win_rate, 'trades': trades_count}
        )
    
    async def alert_overtrading(
        self,
        trades_per_hour: float,
        max_trades_per_hour: float
    ):
        """Alerte sur-trading"""
        if trades_per_hour > max_trades_per_hour * 2:
            level = self.CRITICAL
        elif trades_per_hour > max_trades_per_hour:
            level = self.WARNING
        else:
            return
        
        await self.send_alert(
            level=level,
            title='⚡ Overtrading Detected',
            message=f'Trading frequency: {trades_per_hour:.1f}/hour (max: {max_trades_per_hour:.1f})',
            data={'trades_per_hour': trades_per_hour, 'max': max_trades_per_hour}
        )
    
    async def alert_large_loss(
        self,
        symbol: str,
        pnl_percent: float,
        threshold: float = -5.0
    ):
        """Alerte grosse perte"""
        if pnl_percent < threshold:
            await self.send_alert(
                level=self.CRITICAL if pnl_percent < -10 else self.WARNING,
                title=f'💸 Large Loss on {symbol}',
                message=f'Position closed with {pnl_percent:.2f}% loss',
                data={'symbol': symbol, 'pnl': pnl_percent}
            )
    
    async def alert_capital_threshold(
        self,
        current_capital: float,
        initial_capital: float,
        threshold_pct: float = -20.0
    ):
        """Alerte si capital trop bas"""
        loss_pct = ((current_capital / initial_capital) - 1) * 100
        
        if loss_pct < threshold_pct:
            await self.send_alert(
                level=self.CRITICAL,
                title='🚨 Capital Threshold Breached',
                message=f'Capital: ${current_capital:.2f} ({loss_pct:.1f}% from initial)',
                data={'current': current_capital, 'initial': initial_capital, 'loss_pct': loss_pct},
                force=True
            )
    
    async def alert_system_error(
        self,
        error_type: str,
        error_message: str,
        traceback: Optional[str] = None
    ):
        """Alerte erreur système"""
        await self.send_alert(
            level=self.CRITICAL,
            title=f'💥 System Error: {error_type}',
            message=error_message,
            data={'type': error_type, 'traceback': traceback[:500] if traceback else None}
        )
    
    async def alert_trading_started(self):
        """Alerte démarrage"""
        await self.send_alert(
            level=self.INFO,
            title='✅ Bot Started',
            message='Cryptobot Ultimate v3.0 started successfully',
            force=True
        )
    
    async def alert_trading_stopped(self, reason: str):
        """Alerte arrêt"""
        await self.send_alert(
            level=self.WARNING,
            title='⏹️ Bot Stopped',
            message=f'Reason: {reason}',
            force=True
        )
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Statistiques des alertes"""
        if not self.alert_history:
            return {'total': 0}
        
        by_level = {
            self.CRITICAL: 0,
            self.WARNING: 0,
            self.INFO: 0
        }
        
        for alert in self.alert_history:
            level = alert.get('level', self.INFO)
            by_level[level] = by_level.get(level, 0) + 1
        
        return {
            'total': len(self.alert_history),
            'by_level': by_level,
            'recent': list(self.alert_history)[-5:]  # 5 dernières
        }
