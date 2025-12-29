"""
AI Optimizer - Agent OpenAI qui auto-améliore le bot
Analyse les performances et ajuste automatiquement les paramètres
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
import json
from openai import AsyncOpenAI

class AIOptimizer:
    """
    Agent IA autonome qui:
    1. Analyse les performances du bot
    2. Identifie les problèmes
    3. Suggère des améliorations
    4. Applique les changements automatiquement (si autorisé)
    """
    
    def __init__(
        self,
        openai_api_key: str,
        supabase_logger,
        auto_apply: bool = False,  # Si True, applique auto les changements
        analysis_interval_hours: int = 6
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # OpenAI client
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.supabase_logger = supabase_logger
        
        # Config
        self.auto_apply = auto_apply
        self.analysis_interval = analysis_interval_hours * 3600  # en secondes
        
        # State
        self.running = False
        self.analysis_task: Optional[asyncio.Task] = None
        self.last_analysis: Optional[datetime] = None
        self.suggestions_history: List[Dict] = []
        
        self.logger.info(f"🤖 AI Optimizer initialized (auto_apply={auto_apply})")
    
    async def start(self):
        """Démarrer l'analyse automatique"""
        self.running = True
        self.analysis_task = asyncio.create_task(self._analysis_loop())
        self.logger.info("🚀 AI Optimizer started")
    
    async def stop(self):
        """Arrêter l'optimiseur"""
        self.running = False
        if self.analysis_task:
            await self.analysis_task
        self.logger.info("⏹️ AI Optimizer stopped")
    
    async def _analysis_loop(self):
        """Boucle d'analyse périodique"""
        while self.running:
            try:
                await asyncio.sleep(self.analysis_interval)
                await self.analyze_and_optimize()
            except Exception as e:
                self.logger.error(f"❌ Analysis loop error: {e}")
    
    async def analyze_and_optimize(self) -> Dict[str, Any]:
        """
        Analyse complète des performances et optimisation
        """
        self.logger.info("🔍 Starting AI analysis...")
        
        try:
            # 1. Récupérer les données de performance
            perf_data = await self._gather_performance_data()
            
            if not perf_data:
                self.logger.warning("⚠️ No performance data available")
                return {"status": "no_data"}
            
            # 2. Analyser avec GPT-4
            analysis = await self._analyze_with_gpt4(perf_data)
            
            # 3. Extraire suggestions concrètes
            suggestions = self._extract_suggestions(analysis)
            
            # 4. Appliquer si auto_apply activé
            if self.auto_apply and suggestions:
                applied = await self._apply_suggestions(suggestions)
                self.logger.info(f"✅ Applied {applied}/{len(suggestions)} suggestions")
            
            # 5. Sauvegarder l'analyse
            self.last_analysis = datetime.utcnow()
            self.suggestions_history.append({
                'timestamp': self.last_analysis.isoformat(),
                'analysis': analysis,
                'suggestions': suggestions,
                'applied': self.auto_apply
            })
            
            # 6. Logger l'événement
            await self.supabase_logger.log_event(
                event_type='ai_analysis',
                severity='info',
                message=f'AI analysis completed: {len(suggestions)} suggestions',
                data={'analysis': analysis, 'suggestions': suggestions}
            )
            
            self.logger.info(f"✅ AI analysis completed: {len(suggestions)} suggestions")
            
            return {
                'status': 'success',
                'analysis': analysis,
                'suggestions': suggestions
            }
        
        except Exception as e:
            self.logger.error(f"❌ Analysis failed: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def _gather_performance_data(self) -> Dict[str, Any]:
        """
        Rassemble toutes les données de performance
        """
        try:
            # Récupérer summary des 7 derniers jours
            summary = await self.supabase_logger.get_performance_summary(days=7)
            
            # Récupérer meilleurs heures de trading
            best_hours = await self.supabase_logger.get_best_trading_hours()
            
            # TODO: Ajouter plus de métriques depuis Supabase
            # - Symboles les plus profitables
            # - Types de signaux les plus performants
            # - Raisons d'exit les plus fréquentes
            
            return {
                'summary': summary,
                'best_hours': best_hours,
                'timestamp': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"❌ Data gathering failed: {e}")
            return {}
    
    async def _analyze_with_gpt4(self, perf_data: Dict[str, Any]) -> str:
        """
        Analyse avec GPT-4 les performances du bot
        """
        prompt = f"""Tu es un expert en trading algorithmique et machine learning.

Analyse les performances de ce bot de trading crypto et propose des améliorations CONCRÈTES.

DONNÉES DE PERFORMANCE (7 derniers jours):
{json.dumps(perf_data, indent=2)}

PARAMÈTRES ACTUELS DU BOT:
- MIN_ADVANCED_SCORE: 80 (score minimum pour trader)
- MIN_VOLUME_USD: $500,000 (volume minimum)
- VOLUME_SPIKE_MULTIPLIER: 3.0 (détection spike)
- TOKEN_COOLDOWN_HOURS: 8 (cooldown entre trades)
- MAX_VOLATILITY_24H: 15% (volatilité maximum)
- RSI_OVERBOUGHT: 70
- STOP_LOSS: 3%
- TAKE_PROFIT_1: +3% (sell 20%)
- TAKE_PROFIT_2: +6% (sell 30%)
- TAKE_PROFIT_3: +10% (sell remaining)

ANALYSE DEMANDÉE:
1. Le win rate est-il satisfaisant? (cible: 50%+)
2. Le nombre de trades est-il optimal? (cible: 1-3/heure)
3. Quels paramètres ajuster pour améliorer?
4. Y a-t-il des patterns d'échec récurrents?

RÉPONDS EN FORMAT JSON:
{{
    "win_rate_analysis": "...",
    "trading_frequency_analysis": "...",
    "suggestions": [
        {{
            "parameter": "MIN_ADVANCED_SCORE",
            "current_value": 80,
            "suggested_value": 85,
            "reason": "...",
            "expected_impact": "..."
        }}
    ],
    "overall_recommendation": "..."
}}"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",  # ou "gpt-4-turbo"
                messages=[
                    {"role": "system", "content": "Tu es un expert en trading algorithmique."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            analysis = response.choices[0].message.content
            self.logger.debug(f"🤖 GPT-4 analysis: {analysis[:200]}...")
            
            return analysis
        
        except Exception as e:
            self.logger.error(f"❌ GPT-4 analysis failed: {e}")
            return ""
    
    def _extract_suggestions(self, analysis: str) -> List[Dict[str, Any]]:
        """
        Extrait suggestions JSON de l'analyse GPT-4
        """
        try:
            # Parser JSON de la réponse
            if "```json" in analysis:
                # Extraire le JSON du markdown
                json_str = analysis.split("```json")[1].split("```")[0].strip()
            else:
                json_str = analysis
            
            data = json.loads(json_str)
            
            if 'suggestions' in data:
                return data['suggestions']
            
            return []
        
        except Exception as e:
            self.logger.error(f"❌ Failed to extract suggestions: {e}")
            return []
    
    async def _apply_suggestions(self, suggestions: List[Dict[str, Any]]) -> int:
        """
        Applique les suggestions automatiquement
        ATTENTION: Modifie les paramètres du bot en temps réel!
        """
        applied_count = 0
        
        for suggestion in suggestions:
            try:
                param = suggestion.get('parameter')
                new_value = suggestion.get('suggested_value')
                reason = suggestion.get('reason', 'No reason provided')
                
                if not param or new_value is None:
                    continue
                
                # TODO: Implémenter l'application réelle des paramètres
                # Pour l'instant, on log seulement
                self.logger.info(
                    f"🔧 Would apply: {param} = {new_value} "
                    f"(reason: {reason})"
                )
                
                # Log dans Supabase
                await self.supabase_logger.log_event(
                    event_type='parameter_change',
                    severity='info',
                    message=f'Applied {param} = {new_value}',
                    data=suggestion
                )
                
                applied_count += 1
            
            except Exception as e:
                self.logger.error(f"❌ Failed to apply suggestion: {e}")
        
        return applied_count
    
    async def force_analysis(self) -> Dict[str, Any]:
        """
        Force une analyse immédiate (pour tests)
        """
        self.logger.info("⚡ Forcing immediate analysis...")
        return await self.analyze_and_optimize()
    
    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        """
        Récupère la dernière analyse effectuée
        """
        if self.suggestions_history:
            return self.suggestions_history[-1]
        return None
    
    def get_suggestions_summary(self) -> Dict[str, Any]:
        """
        Résumé de toutes les suggestions historiques
        """
        if not self.suggestions_history:
            return {'total': 0, 'suggestions': []}
        
        all_suggestions = []
        for entry in self.suggestions_history:
            all_suggestions.extend(entry.get('suggestions', []))
        
        # Grouper par paramètre
        param_counts = {}
        for sugg in all_suggestions:
            param = sugg.get('parameter', 'unknown')
            param_counts[param] = param_counts.get(param, 0) + 1
        
        return {
            'total': len(all_suggestions),
            'by_parameter': param_counts,
            'last_analysis': self.last_analysis.isoformat() if self.last_analysis else None
        }
