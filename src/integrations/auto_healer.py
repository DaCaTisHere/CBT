"""
Auto Healer - Système d'auto-réparation
Détecte et corrige automatiquement les problèmes
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging
from enum import Enum

class HealthStatus(Enum):
    """États de santé du système"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"

class AutoHealer:
    """
    Système d'auto-réparation qui:
    1. Monitore la santé du bot
    2. Détecte les anomalies
    3. Applique des corrections automatiques
    4. Escalade si nécessaire
    """
    
    def __init__(
        self,
        supabase_logger,
        smart_alerts,
        check_interval_seconds: int = 60
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.supabase_logger = supabase_logger
        self.smart_alerts = smart_alerts
        
        # Config
        self.check_interval = check_interval_seconds
        
        # State
        self.running = False
        self.health_task: Optional[asyncio.Task] = None
        self.status = HealthStatus.HEALTHY
        self.issues: List[Dict] = []
        self.fixes_applied: List[Dict] = []
        
        # Thresholds
        self.MAX_CONSECUTIVE_LOSSES = 10
        self.MAX_DRAWDOWN_PCT = 25.0
        self.MIN_WIN_RATE_PCT = 30.0
        self.MAX_TRADES_PER_HOUR = 5.0
        
        self.logger.info("🏥 Auto Healer initialized")
    
    async def start(self):
        """Démarrer le monitoring"""
        self.running = True
        self.health_task = asyncio.create_task(self._health_check_loop())
        self.logger.info("🚀 Auto Healer started")
    
    async def stop(self):
        """Arrêter le healer"""
        self.running = False
        if self.health_task:
            await self.health_task
        self.logger.info("⏹️ Auto Healer stopped")
    
    async def _health_check_loop(self):
        """Boucle de vérification santé"""
        while self.running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_health()
            except Exception as e:
                self.logger.error(f"❌ Health check loop error: {e}")
    
    async def check_health(self) -> HealthStatus:
        """
        Vérifie la santé globale du système
        """
        try:
            self.logger.debug("🔍 Running health check...")
            
            # Reset issues
            self.issues.clear()
            
            # 1. Vérifier performance récente
            await self._check_performance()
            
            # 2. Vérifier drawdown
            await self._check_drawdown()
            
            # 3. Vérifier sur-trading
            await self._check_overtrading()
            
            # 4. Vérifier pertes consécutives
            await self._check_consecutive_losses()
            
            # 5. Déterminer status global
            self._update_status()
            
            # 6. Appliquer corrections si nécessaire
            if self.status != HealthStatus.HEALTHY:
                await self._apply_fixes()
            
            return self.status
        
        except Exception as e:
            self.logger.error(f"❌ Health check failed: {e}")
            return HealthStatus.DOWN
    
    async def _check_performance(self):
        """Vérifie le win rate récent"""
        try:
            perf_data = await self.supabase_logger.get_performance_summary(days=7)
            
            if not perf_data:
                return
            
            win_rate = perf_data.get('avg_win_rate', 0)
            
            if win_rate < self.MIN_WIN_RATE_PCT:
                self.issues.append({
                    'type': 'low_win_rate',
                    'severity': 'critical' if win_rate < 20 else 'warning',
                    'value': win_rate,
                    'message': f'Win rate trop bas: {win_rate:.1f}% (min: {self.MIN_WIN_RATE_PCT}%)'
                })
        
        except Exception as e:
            self.logger.error(f"❌ Performance check failed: {e}")
    
    async def _check_drawdown(self):
        """Vérifie le drawdown (perte max depuis pic)"""
        try:
            # TODO: Calculer depuis Supabase
            # Pour l'instant, placeholder
            pass
        
        except Exception as e:
            self.logger.error(f"❌ Drawdown check failed: {e}")
    
    async def _check_overtrading(self):
        """Vérifie le sur-trading"""
        try:
            perf_data = await self.supabase_logger.get_performance_summary(days=1)
            
            if not perf_data:
                return
            
            total_trades = perf_data.get('total_trades', 0)
            trades_per_hour = total_trades / 24
            
            if trades_per_hour > self.MAX_TRADES_PER_HOUR:
                self.issues.append({
                    'type': 'overtrading',
                    'severity': 'critical' if trades_per_hour > self.MAX_TRADES_PER_HOUR * 2 else 'warning',
                    'value': trades_per_hour,
                    'message': f'Sur-trading: {trades_per_hour:.1f} trades/heure (max: {self.MAX_TRADES_PER_HOUR})'
                })
        
        except Exception as e:
            self.logger.error(f"❌ Overtrading check failed: {e}")
    
    async def _check_consecutive_losses(self):
        """Vérifie les pertes consécutives"""
        try:
            # TODO: Query Supabase pour derniers trades
            # Pour l'instant, placeholder
            pass
        
        except Exception as e:
            self.logger.error(f"❌ Consecutive losses check failed: {e}")
    
    def _update_status(self):
        """Met à jour le status global basé sur les issues"""
        if not self.issues:
            self.status = HealthStatus.HEALTHY
            return
        
        # Compter par severity
        critical_count = sum(1 for issue in self.issues if issue['severity'] == 'critical')
        warning_count = sum(1 for issue in self.issues if issue['severity'] == 'warning')
        
        if critical_count >= 2:
            self.status = HealthStatus.CRITICAL
        elif critical_count >= 1:
            self.status = HealthStatus.DEGRADED
        elif warning_count >= 3:
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.HEALTHY
    
    async def _apply_fixes(self):
        """Applique des corrections automatiques"""
        for issue in self.issues:
            issue_type = issue['type']
            
            if issue_type == 'low_win_rate':
                await self._fix_low_win_rate(issue)
            
            elif issue_type == 'overtrading':
                await self._fix_overtrading(issue)
            
            # Log dans Supabase
            await self.supabase_logger.log_event(
                event_type='auto_healing',
                severity=issue['severity'],
                message=f"Applied fix for {issue_type}",
                data=issue
            )
            
            # Alerte
            await self.smart_alerts.send_alert(
                level=self.smart_alerts.CRITICAL if issue['severity'] == 'critical' else self.smart_alerts.WARNING,
                title=f"🏥 Auto-Healing Applied",
                message=issue['message'],
                data=issue
            )
    
    async def _fix_low_win_rate(self, issue: Dict):
        """Correction: Win rate trop bas"""
        win_rate = issue['value']
        
        if win_rate < 20:
            # Critique: Augmenter drastiquement le score minimum
            fix = {
                'action': 'increase_min_score',
                'old_value': 80,
                'new_value': 90,
                'reason': f'Win rate critique ({win_rate:.1f}%)'
            }
        else:
            # Warning: Augmenter modérément
            fix = {
                'action': 'increase_min_score',
                'old_value': 80,
                'new_value': 85,
                'reason': f'Win rate bas ({win_rate:.1f}%)'
            }
        
        self.fixes_applied.append(fix)
        self.logger.info(f"🔧 Applied fix: {fix['action']} to {fix['new_value']}")
        
        # TODO: Appliquer réellement au momentum detector
    
    async def _fix_overtrading(self, issue: Dict):
        """Correction: Sur-trading"""
        trades_per_hour = issue['value']
        
        if trades_per_hour > self.MAX_TRADES_PER_HOUR * 2:
            # Critique: Augmenter drastiquement cooldown
            fix = {
                'action': 'increase_cooldown',
                'old_value': 8,
                'new_value': 12,
                'reason': f'Sur-trading critique ({trades_per_hour:.1f} trades/h)'
            }
        else:
            # Warning: Augmenter modérément
            fix = {
                'action': 'increase_cooldown',
                'old_value': 8,
                'new_value': 10,
                'reason': f'Sur-trading ({trades_per_hour:.1f} trades/h)'
            }
        
        self.fixes_applied.append(fix)
        self.logger.info(f"🔧 Applied fix: {fix['action']} to {fix['new_value']}")
        
        # TODO: Appliquer réellement au momentum detector
    
    def get_health_report(self) -> Dict[str, Any]:
        """Rapport de santé complet"""
        return {
            'status': self.status.value,
            'issues_count': len(self.issues),
            'issues': self.issues,
            'fixes_applied_count': len(self.fixes_applied),
            'recent_fixes': self.fixes_applied[-5:] if self.fixes_applied else []
        }
