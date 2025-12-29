"""
Supabase Logger - Log TOUT en temps réel
Permet analytics avancées et monitoring
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
from supabase import create_client, Client
import json

class SupabaseLogger:
    """
    Logger ultra-performant vers Supabase
    Stocke TOUS les événements du bot pour analytics avancées
    """
    
    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        batch_size: int = 50,
        flush_interval: int = 30
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Supabase client
        try:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            self.logger.info("✅ Supabase connected")
        except Exception as e:
            self.logger.error(f"❌ Supabase connection failed: {e}")
            self.supabase = None
        
        # Batch config
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # Buffers pour batch inserts (performance++)
        self.trades_buffer: List[Dict] = []
        self.signals_buffer: List[Dict] = []
        self.metrics_buffer: List[Dict] = []
        self.events_buffer: List[Dict] = []
        
        # Background task
        self.flush_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def start(self):
        """Start background flushing task"""
        if not self.supabase:
            self.logger.warning("⚠️ Supabase not connected, logger disabled")
            return
        
        self.running = True
        self.flush_task = asyncio.create_task(self._flush_loop())
        self.logger.info("🚀 Supabase logger started")
    
    async def stop(self):
        """Stop and flush remaining data"""
        self.running = False
        if self.flush_task:
            await self.flush_task
        await self._flush_all()
        self.logger.info("⏹️ Supabase logger stopped")
    
    async def _flush_loop(self):
        """Background task qui flush périodiquement"""
        while self.running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_all()
            except Exception as e:
                self.logger.error(f"❌ Flush loop error: {e}")
    
    async def _flush_all(self):
        """Flush tous les buffers vers Supabase"""
        if not self.supabase:
            return
        
        try:
            # Flush trades
            if self.trades_buffer:
                self.supabase.table('trades').insert(self.trades_buffer).execute()
                self.logger.debug(f"📊 Flushed {len(self.trades_buffer)} trades")
                self.trades_buffer.clear()
            
            # Flush signals
            if self.signals_buffer:
                self.supabase.table('signals').insert(self.signals_buffer).execute()
                self.logger.debug(f"📡 Flushed {len(self.signals_buffer)} signals")
                self.signals_buffer.clear()
            
            # Flush metrics
            if self.metrics_buffer:
                self.supabase.table('metrics').insert(self.metrics_buffer).execute()
                self.logger.debug(f"📈 Flushed {len(self.metrics_buffer)} metrics")
                self.metrics_buffer.clear()
            
            # Flush events
            if self.events_buffer:
                self.supabase.table('events').insert(self.events_buffer).execute()
                self.logger.debug(f"📝 Flushed {len(self.events_buffer)} events")
                self.events_buffer.clear()
        
        except Exception as e:
            self.logger.error(f"❌ Flush error: {e}")
    
    # ==================== LOG METHODS ====================
    
    async def log_trade_entry(
        self,
        symbol: str,
        entry_price: float,
        amount: float,
        signal_score: float,
        signal_type: str,
        indicators: Dict[str, Any]
    ):
        """Log trade entry"""
        trade = {
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'action': 'entry',
            'price': entry_price,
            'amount': amount,
            'signal_score': signal_score,
            'signal_type': signal_type,
            'indicators': json.dumps(indicators),
            'status': 'open'
        }
        
        self.trades_buffer.append(trade)
        if len(self.trades_buffer) >= self.batch_size:
            await self._flush_all()
    
    async def log_trade_exit(
        self,
        symbol: str,
        exit_price: float,
        pnl_percent: float,
        exit_reason: str,
        hold_time_minutes: float
    ):
        """Log trade exit"""
        trade = {
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'action': 'exit',
            'price': exit_price,
            'pnl_percent': pnl_percent,
            'exit_reason': exit_reason,
            'hold_time_minutes': hold_time_minutes,
            'status': 'closed'
        }
        
        self.trades_buffer.append(trade)
        if len(self.trades_buffer) >= self.batch_size:
            await self._flush_all()
    
    async def log_signal(
        self,
        symbol: str,
        signal_type: str,
        score: float,
        indicators: Dict[str, Any],
        action_taken: str
    ):
        """Log signal détecté"""
        signal = {
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'signal_type': signal_type,
            'score': score,
            'indicators': json.dumps(indicators),
            'action_taken': action_taken
        }
        
        self.signals_buffer.append(signal)
        if len(self.signals_buffer) >= self.batch_size:
            await self._flush_all()
    
    async def log_metrics(
        self,
        win_rate: float,
        total_trades: int,
        capital: float,
        daily_pnl: float,
        active_positions: int,
        avg_win: float,
        avg_loss: float
    ):
        """Log métriques globales"""
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'win_rate': win_rate,
            'total_trades': total_trades,
            'capital': capital,
            'daily_pnl': daily_pnl,
            'active_positions': active_positions,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }
        
        self.metrics_buffer.append(metrics)
        if len(self.metrics_buffer) >= self.batch_size:
            await self._flush_all()
    
    async def log_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """Log événement système"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'severity': severity,
            'message': message,
            'data': json.dumps(data) if data else None
        }
        
        self.events_buffer.append(event)
        if len(self.events_buffer) >= self.batch_size:
            await self._flush_all()
    
    # ==================== ANALYTICS QUERIES ====================
    
    async def get_performance_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Récupère résumé performance des N derniers jours
        """
        if not self.supabase:
            return {}
        
        try:
            # Query metrics des derniers N jours
            response = self.supabase.table('metrics')\
                .select('*')\
                .gte('timestamp', f'now() - interval \'{days} days\'')\
                .order('timestamp', desc=True)\
                .limit(1000)\
                .execute()
            
            if response.data:
                metrics = response.data
                return {
                    'avg_win_rate': sum(m['win_rate'] for m in metrics) / len(metrics),
                    'total_trades': max(m['total_trades'] for m in metrics),
                    'current_capital': metrics[0]['capital'],
                    'total_pnl': sum(m['daily_pnl'] for m in metrics)
                }
            
            return {}
        
        except Exception as e:
            self.logger.error(f"❌ Query error: {e}")
            return {}
    
    async def get_best_trading_hours(self) -> List[int]:
        """
        Analyse les heures les plus profitables
        Retourne liste des heures UTC les plus rentables
        """
        if not self.supabase:
            return []
        
        try:
            # Query trades avec PnL positif
            response = self.supabase.table('trades')\
                .select('timestamp, pnl_percent')\
                .gt('pnl_percent', 0)\
                .execute()
            
            if response.data:
                # Extraire heures
                from collections import Counter
                hours = []
                for trade in response.data:
                    timestamp = datetime.fromisoformat(trade['timestamp'])
                    hours.append(timestamp.hour)
                
                # Top 5 heures
                hour_counts = Counter(hours)
                return [h for h, _ in hour_counts.most_common(5)]
            
            return []
        
        except Exception as e:
            self.logger.error(f"❌ Query error: {e}")
            return []
