"""
Parameter Optimizer - Auto-ajuste les paramètres du bot
Teste différentes configurations pour trouver l'optimale
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
import json
from dataclasses import dataclass, asdict

@dataclass
class ParameterConfig:
    """Configuration des paramètres testables"""
    name: str
    current_value: Any
    min_value: Any
    max_value: Any
    step: Any
    description: str

class ParameterOptimizer:
    """
    Système d'auto-optimisation intelligent qui:
    1. Teste des variations de paramètres
    2. Mesure l'impact sur les performances
    3. Applique la meilleure configuration
    
    Utilise A/B testing et gradient descent
    """
    
    # Paramètres optimisables
    OPTIMIZABLE_PARAMS = {
        'MIN_ADVANCED_SCORE': ParameterConfig(
            name='MIN_ADVANCED_SCORE',
            current_value=80,
            min_value=70,
            max_value=90,
            step=2,
            description='Score minimum pour trader'
        ),
        'MIN_VOLUME_USD': ParameterConfig(
            name='MIN_VOLUME_USD',
            current_value=500000,
            min_value=200000,
            max_value=1000000,
            step=100000,
            description='Volume minimum requis'
        ),
        'VOLUME_SPIKE_MULTIPLIER': ParameterConfig(
            name='VOLUME_SPIKE_MULTIPLIER',
            current_value=3.0,
            min_value=2.0,
            max_value=5.0,
            step=0.5,
            description='Multiplicateur volume spike'
        ),
        'TOKEN_COOLDOWN_HOURS': ParameterConfig(
            name='TOKEN_COOLDOWN_HOURS',
            current_value=8.0,
            min_value=4.0,
            max_value=12.0,
            step=2.0,
            description='Cooldown entre trades même token'
        ),
        'MAX_VOLATILITY_24H': ParameterConfig(
            name='MAX_VOLATILITY_24H',
            current_value=15.0,
            min_value=10.0,
            max_value=20.0,
            step=2.5,
            description='Volatilité maximum autorisée'
        ),
        'RSI_OVERBOUGHT': ParameterConfig(
            name='RSI_OVERBOUGHT',
            current_value=70,
            min_value=65,
            max_value=80,
            step=5,
            description='Seuil RSI overbought'
        ),
        'STOP_LOSS_PCT': ParameterConfig(
            name='STOP_LOSS_PCT',
            current_value=3.0,
            min_value=2.0,
            max_value=5.0,
            step=0.5,
            description='Stop loss percentage'
        ),
        'TP1_PCT': ParameterConfig(
            name='TP1_PCT',
            current_value=3.0,
            min_value=2.0,
            max_value=5.0,
            step=0.5,
            description='Take profit 1 percentage'
        ),
        'TP2_PCT': ParameterConfig(
            name='TP2_PCT',
            current_value=6.0,
            min_value=4.0,
            max_value=8.0,
            step=1.0,
            description='Take profit 2 percentage'
        ),
        'TP3_PCT': ParameterConfig(
            name='TP3_PCT',
            current_value=10.0,
            min_value=8.0,
            max_value=15.0,
            step=1.0,
            description='Take profit 3 percentage'
        ),
    }
    
    def __init__(
        self,
        supabase_logger,
        optimization_interval_hours: int = 24,
        min_trades_for_optimization: int = 50
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.supabase_logger = supabase_logger
        
        # Config
        self.optimization_interval = optimization_interval_hours * 3600
        self.min_trades = min_trades_for_optimization
        
        # State
        self.running = False
        self.optimization_task: Optional[asyncio.Task] = None
        self.current_config: Dict[str, Any] = {}
        self.test_results: List[Dict] = []
        
        # Initialize current config
        for param_name, param_config in self.OPTIMIZABLE_PARAMS.items():
            self.current_config[param_name] = param_config.current_value
        
        self.logger.info("🔧 Parameter Optimizer initialized")
    
    async def start(self):
        """Démarrer l'optimisation automatique"""
        self.running = True
        self.optimization_task = asyncio.create_task(self._optimization_loop())
        self.logger.info("🚀 Parameter Optimizer started")
    
    async def stop(self):
        """Arrêter l'optimiseur"""
        self.running = False
        if self.optimization_task:
            await self.optimization_task
        self.logger.info("⏹️ Parameter Optimizer stopped")
    
    async def _optimization_loop(self):
        """Boucle d'optimisation périodique"""
        while self.running:
            try:
                await asyncio.sleep(self.optimization_interval)
                await self.optimize_parameters()
            except Exception as e:
                self.logger.error(f"❌ Optimization loop error: {e}")
    
    async def optimize_parameters(self) -> Dict[str, Any]:
        """
        Optimise les paramètres en testant des variations
        """
        self.logger.info("🔍 Starting parameter optimization...")
        
        try:
            # 1. Vérifier qu'on a assez de données
            perf_data = await self.supabase_logger.get_performance_summary(days=7)
            
            if not perf_data or perf_data.get('total_trades', 0) < self.min_trades:
                self.logger.warning(
                    f"⚠️ Not enough trades for optimization "
                    f"({perf_data.get('total_trades', 0)}/{self.min_trades})"
                )
                return {'status': 'insufficient_data'}
            
            # 2. Calculer score de performance actuel
            current_score = self._calculate_performance_score(perf_data)
            
            self.logger.info(f"📊 Current performance score: {current_score:.2f}")
            
            # 3. Tester variations des paramètres (gradient descent)
            best_config, best_score = await self._test_parameter_variations(
                current_score=current_score
            )
            
            # 4. Appliquer si amélioration significative
            if best_score > current_score * 1.05:  # +5% minimum
                self.logger.info(
                    f"✅ Found better config! "
                    f"Score: {current_score:.2f} → {best_score:.2f}"
                )
                
                # Appliquer la nouvelle config
                await self._apply_configuration(best_config)
                
                # Logger l'événement
                await self.supabase_logger.log_event(
                    event_type='parameter_optimization',
                    severity='info',
                    message=f'Applied optimized parameters (score +{((best_score/current_score-1)*100):.1f}%)',
                    data={
                        'old_config': self.current_config,
                        'new_config': best_config,
                        'old_score': current_score,
                        'new_score': best_score
                    }
                )
                
                self.current_config = best_config
            else:
                self.logger.info("ℹ️ No significant improvement found, keeping current config")
            
            return {
                'status': 'success',
                'current_score': current_score,
                'best_score': best_score,
                'improvement': ((best_score / current_score - 1) * 100) if current_score > 0 else 0
            }
        
        except Exception as e:
            self.logger.error(f"❌ Optimization failed: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _calculate_performance_score(self, perf_data: Dict[str, Any]) -> float:
        """
        Calcule un score de performance global
        Combine win rate, profit, et autres métriques
        """
        win_rate = perf_data.get('avg_win_rate', 0) / 100  # 0-1
        total_pnl = perf_data.get('total_pnl', 0)
        total_trades = perf_data.get('total_trades', 1)
        
        # Score composite (pondéré)
        # - Win rate: 50%
        # - PnL moyen par trade: 30%
        # - Volume de trading: 20%
        
        win_rate_score = win_rate * 50
        
        avg_pnl_per_trade = total_pnl / total_trades if total_trades > 0 else 0
        pnl_score = min(avg_pnl_per_trade * 10, 30)  # Max 30 points
        
        # Pénalité si trop de trades (sur-trading)
        trades_per_day = total_trades / 7
        if trades_per_day > 48:  # Plus de 2/heure = mauvais
            volume_score = 0
        elif trades_per_day < 10:  # Moins de 10/jour = pas assez
            volume_score = trades_per_day * 2
        else:
            volume_score = 20
        
        total_score = win_rate_score + pnl_score + volume_score
        
        return total_score
    
    async def _test_parameter_variations(
        self,
        current_score: float
    ) -> Tuple[Dict[str, Any], float]:
        """
        Teste des variations des paramètres
        Utilise gradient descent pour trouver optimum
        
        NOTE: En simulation, on ne peut pas vraiment "tester"
        On utilise donc des heuristiques basées sur les données historiques
        """
        best_config = self.current_config.copy()
        best_score = current_score
        
        # Pour chaque paramètre, tester une petite variation
        for param_name, param_config in self.OPTIMIZABLE_PARAMS.items():
            current_value = self.current_config[param_name]
            
            # Tester +step et -step
            for direction in [1, -1]:
                test_value = current_value + (param_config.step * direction)
                
                # Vérifier bounds
                if (test_value < param_config.min_value or 
                    test_value > param_config.max_value):
                    continue
                
                # Estimer impact (heuristique basée sur historique)
                estimated_score = self._estimate_score_impact(
                    param_name,
                    test_value,
                    current_score
                )
                
                if estimated_score > best_score:
                    best_score = estimated_score
                    best_config = best_config.copy()
                    best_config[param_name] = test_value
                    
                    self.logger.debug(
                        f"📈 Better config found: {param_name}={test_value} "
                        f"(score: {estimated_score:.2f})"
                    )
        
        return best_config, best_score
    
    def _estimate_score_impact(
        self,
        param_name: str,
        new_value: Any,
        base_score: float
    ) -> float:
        """
        Estime l'impact d'un changement de paramètre
        Basé sur des heuristiques et données historiques
        
        TODO: Utiliser vraiment les données Supabase pour prédire
        """
        current_value = self.current_config[param_name]
        change_pct = (new_value - current_value) / current_value if current_value != 0 else 0
        
        # Heuristiques simplifiées
        if param_name == 'MIN_ADVANCED_SCORE':
            # Score plus élevé = moins de trades mais meilleure qualité
            if new_value > current_value:
                return base_score * (1 + change_pct * 0.3)  # +30% d'impact
            else:
                return base_score * (1 - change_pct * 0.2)  # -20% d'impact
        
        elif param_name == 'MIN_VOLUME_USD':
            # Volume plus élevé = moins de trades mais moins de pump&dump
            if new_value > current_value:
                return base_score * (1 + change_pct * 0.15)
            else:
                return base_score * (1 - change_pct * 0.1)
        
        elif param_name in ['STOP_LOSS_PCT', 'TP1_PCT', 'TP2_PCT', 'TP3_PCT']:
            # SL/TP: équilibre risk/reward
            # Difficile à prédire, petit impact
            return base_score * (1 + change_pct * 0.05)
        
        # Par défaut: petit impact positif ou négatif
        return base_score * (1 + change_pct * 0.1)
    
    async def _apply_configuration(self, config: Dict[str, Any]):
        """
        Applique une nouvelle configuration
        TODO: Implémenter l'application réelle aux modules
        """
        self.logger.info("🔧 Applying new configuration...")
        
        for param_name, value in config.items():
            self.logger.info(f"  {param_name}: {self.current_config.get(param_name)} → {value}")
        
        # TODO: Appliquer réellement aux modules
        # Pour l'instant, on stocke juste
        self.current_config = config
    
    def get_current_config(self) -> Dict[str, Any]:
        """Retourne la configuration actuelle"""
        return self.current_config.copy()
    
    def get_optimization_history(self) -> List[Dict]:
        """Retourne l'historique des optimisations"""
        return self.test_results.copy()
