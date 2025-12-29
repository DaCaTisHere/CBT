"""
Autonomous Manager - Gestionnaire de tous les systèmes autonomes
Point d'entrée unique pour: Supabase, OpenAI, Alertes, Auto-healing
"""
import asyncio
from typing import Optional
import logging
import os
from dotenv import load_dotenv

# Import tous les systèmes
from src.integrations.supabase_logger import SupabaseLogger
from src.integrations.ai_optimizer import AIOptimizer
from src.integrations.parameter_optimizer import ParameterOptimizer
from src.integrations.smart_alerts import SmartAlerts
from src.integrations.auto_healer import AutoHealer

load_dotenv()

class AutonomousManager:
    """
    Manager central qui orchestre TOUS les systèmes autonomes
    
    Systèmes gérés:
    - Supabase Logger (analytics temps réel)
    - AI Optimizer (analyse GPT-4)
    - Parameter Optimizer (auto-tuning)
    - Smart Alerts (notifications)
    - Auto Healer (auto-réparation)
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # État
        self.running = False
        self.systems_status = {}
        
        # Systèmes
        self.supabase_logger: Optional[SupabaseLogger] = None
        self.ai_optimizer: Optional[AIOptimizer] = None
        self.parameter_optimizer: Optional[ParameterOptimizer] = None
        self.smart_alerts: Optional[SmartAlerts] = None
        self.auto_healer: Optional[AutoHealer] = None
        
        self.logger.info("🤖 Autonomous Manager initialized")
    
    async def initialize(self) -> bool:
        """
        Initialise TOUS les systèmes autonomes
        Retourne True si au moins un système démarre
        """
        self.logger.info("🚀 Initializing autonomous systems...")
        
        try:
            # 1. Supabase Logger (fondation)
            self.supabase_logger = await self._init_supabase_logger()
            
            # 2. Smart Alerts (notifications)
            self.smart_alerts = await self._init_smart_alerts()
            
            # 3. AI Optimizer (analyse GPT-4)
            self.ai_optimizer = await self._init_ai_optimizer()
            
            # 4. Parameter Optimizer (auto-tuning)
            self.parameter_optimizer = await self._init_parameter_optimizer()
            
            # 5. Auto Healer (auto-réparation)
            self.auto_healer = await self._init_auto_healer()
            
            # Démarrer tous les systèmes actifs
            await self._start_all_systems()
            
            # Envoyer alerte de démarrage
            if self.smart_alerts:
                await self.smart_alerts.alert_trading_started()
            
            # Status
            active_count = sum(1 for status in self.systems_status.values() if status)
            self.logger.info(
                f"✅ Autonomous systems ready: {active_count}/{len(self.systems_status)} active"
            )
            
            return active_count > 0
        
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize autonomous systems: {e}")
            return False
    
    async def _init_supabase_logger(self) -> Optional[SupabaseLogger]:
        """Initialise Supabase Logger"""
        try:
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            if not supabase_url or not supabase_key:
                self.logger.warning("⚠️ Supabase credentials not found, logger disabled")
                self.systems_status['supabase'] = False
                return None
            
            logger = SupabaseLogger(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
                batch_size=50,
                flush_interval=30
            )
            
            self.systems_status['supabase'] = True
            self.logger.info("✅ Supabase Logger ready")
            return logger
        
        except Exception as e:
            self.logger.error(f"❌ Supabase Logger init failed: {e}")
            self.systems_status['supabase'] = False
            return None
    
    async def _init_smart_alerts(self) -> Optional[SmartAlerts]:
        """Initialise Smart Alerts"""
        try:
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
            telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
            webhook_url = os.getenv('WEBHOOK_URL')
            
            if not telegram_token and not webhook_url:
                self.logger.warning("⚠️ No alert channels configured")
                self.systems_status['alerts'] = False
                return None
            
            alerts = SmartAlerts(
                telegram_bot_token=telegram_token if telegram_token else None,
                telegram_chat_id=telegram_chat if telegram_chat else None,
                webhook_url=webhook_url if webhook_url else None
            )
            
            self.systems_status['alerts'] = True
            self.logger.info("✅ Smart Alerts ready")
            return alerts
        
        except Exception as e:
            self.logger.error(f"❌ Smart Alerts init failed: {e}")
            self.systems_status['alerts'] = False
            return None
    
    async def _init_ai_optimizer(self) -> Optional[AIOptimizer]:
        """Initialise AI Optimizer"""
        try:
            openai_key = os.getenv('OPENAI_API_KEY')
            enable_ai = os.getenv('ENABLE_AI_OPTIMIZER', 'False').lower() == 'true'
            
            if not openai_key or not enable_ai:
                self.logger.info("ℹ️ AI Optimizer disabled")
                self.systems_status['ai_optimizer'] = False
                return None
            
            if not self.supabase_logger:
                self.logger.warning("⚠️ AI Optimizer needs Supabase Logger")
                self.systems_status['ai_optimizer'] = False
                return None
            
            auto_apply = os.getenv('AI_AUTO_APPLY_SUGGESTIONS', 'False').lower() == 'true'
            
            optimizer = AIOptimizer(
                openai_api_key=openai_key,
                supabase_logger=self.supabase_logger,
                auto_apply=auto_apply,
                analysis_interval_hours=6
            )
            
            self.systems_status['ai_optimizer'] = True
            self.logger.info(f"✅ AI Optimizer ready (auto_apply={auto_apply})")
            return optimizer
        
        except Exception as e:
            self.logger.error(f"❌ AI Optimizer init failed: {e}")
            self.systems_status['ai_optimizer'] = False
            return None
    
    async def _init_parameter_optimizer(self) -> Optional[ParameterOptimizer]:
        """Initialise Parameter Optimizer"""
        try:
            if not self.supabase_logger:
                self.logger.warning("⚠️ Parameter Optimizer needs Supabase Logger")
                self.systems_status['param_optimizer'] = False
                return None
            
            optimizer = ParameterOptimizer(
                supabase_logger=self.supabase_logger,
                optimization_interval_hours=24,
                min_trades_for_optimization=50
            )
            
            self.systems_status['param_optimizer'] = True
            self.logger.info("✅ Parameter Optimizer ready")
            return optimizer
        
        except Exception as e:
            self.logger.error(f"❌ Parameter Optimizer init failed: {e}")
            self.systems_status['param_optimizer'] = False
            return None
    
    async def _init_auto_healer(self) -> Optional[AutoHealer]:
        """Initialise Auto Healer"""
        try:
            if not self.supabase_logger or not self.smart_alerts:
                self.logger.warning("⚠️ Auto Healer needs Supabase + Alerts")
                self.systems_status['auto_healer'] = False
                return None
            
            healer = AutoHealer(
                supabase_logger=self.supabase_logger,
                smart_alerts=self.smart_alerts,
                check_interval_seconds=60
            )
            
            self.systems_status['auto_healer'] = True
            self.logger.info("✅ Auto Healer ready")
            return healer
        
        except Exception as e:
            self.logger.error(f"❌ Auto Healer init failed: {e}")
            self.systems_status['auto_healer'] = False
            return None
    
    async def _start_all_systems(self):
        """Démarre tous les systèmes actifs"""
        if self.supabase_logger:
            await self.supabase_logger.start()
        
        if self.ai_optimizer:
            await self.ai_optimizer.start()
        
        if self.parameter_optimizer:
            await self.parameter_optimizer.start()
        
        if self.auto_healer:
            await self.auto_healer.start()
    
    async def stop(self):
        """Arrête tous les systèmes"""
        self.logger.info("⏹️ Stopping autonomous systems...")
        
        if self.auto_healer:
            await self.auto_healer.stop()
        
        if self.parameter_optimizer:
            await self.parameter_optimizer.stop()
        
        if self.ai_optimizer:
            await self.ai_optimizer.stop()
        
        if self.supabase_logger:
            await self.supabase_logger.stop()
        
        if self.smart_alerts:
            await self.smart_alerts.alert_trading_stopped("Normal shutdown")
        
        self.logger.info("✅ All autonomous systems stopped")
    
    def get_systems_status(self) -> dict:
        """Status de tous les systèmes"""
        return {
            'systems': self.systems_status,
            'active_count': sum(1 for status in self.systems_status.values() if status),
            'total_count': len(self.systems_status)
        }
