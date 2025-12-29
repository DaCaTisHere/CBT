# 🤖 CRYPTOBOT ULTIMATE - FICHIER DE RELANCE

> **Ce fichier permet de reprendre le projet à tout moment, même sans mémoire du contexte précédent.**

---

## 📍 INFORMATIONS ESSENTIELLES

### URLs Importantes
- **Dashboard Railway**: https://railway.com/project/27ccd7e9-54e2-4a6e-86b1-beb1e999a354
- **Healthcheck (voir stats en direct)**: https://cryptobot-ultimate-production.up.railway.app/
- **Service ID**: cd34f953-c5a9-4b93-97b4-dcd26d795139

### Identifiants Projet
- **Projet Railway**: cryptobot-ultimate
- **Environnement**: production
- **Région**: asia-southeast1

---

## 🎯 OBJECTIF DU BOT

Bot de trading crypto automatisé qui:
1. **Détecte** les mouvements de momentum sur Binance (tokens qui montent)
2. **Analyse** avec du Machine Learning pour prédire les bonnes opportunités
3. **Trade** automatiquement en simulation (paper trading)
4. **Apprend** de chaque trade pour s'améliorer

### Mode Actuel: SIMULATION
- Capital virtuel: $10,000
- Aucun argent réel utilisé
- Objectif: valider la stratégie pendant 60-90 jours

---

## 🏗️ ARCHITECTURE DU PROJET

```
src/
├── main.py                    # Point d'entrée
├── healthcheck.py             # Dashboard web (port 8080)
├── core/
│   ├── config.py              # Configuration (variables d'environnement)
│   ├── orchestrator.py        # ⭐ CERVEAU - coordonne tout
│   └── risk_manager.py        # Gestion des risques
├── data/
│   ├── binance_websocket.py   # Prix en temps réel
│   └── storage/               # Base de données SQLite
├── modules/
│   ├── momentum_detector.py   # ⭐ DÉTECTION - trouve les opportunités
│   ├── ml_predictor/          # Machine Learning
│   ├── sniper/                # Sniper bot (nouveaux tokens)
│   ├── news_trader/           # Trading sur les news
│   ├── sentiment/             # Analyse de sentiment (désactivé)
│   ├── arbitrage/             # Arbitrage (désactivé)
│   ├── copy_trading/          # Copy trading (désactivé)
│   └── defi_optimizer/        # DeFi (désactivé)
├── trading/
│   ├── paper_trader.py        # ⭐ EXÉCUTION - trades simulés
│   ├── real_trainer.py        # Entraînement ML continu
│   └── ml_model.py            # Modèle ML
└── notifications/
    └── telegram_bot.py        # Alertes Telegram
```

---

## ⚙️ STRATÉGIE DE TRADING ACTUELLE (v2.0 - Ultra Optimisée)

### Filtres d'Entrée AVANCÉS (dans `orchestrator.py`)
```python
# On achète SEULEMENT si TOUS les filtres passent:
- Score minimum: 55/100 (basé sur TOUS les indicateurs)
- MACD: bullish ou neutral (pas bearish)
- EMA Trend: aligné (pas bearish_cross ou bearish)
- BTC Correlation: positive (trade avec le marché!)
- RSI: entre 25-70 (pas surachat/survente extrême)
- Stochastic RSI: < 80 (pas surachat)
- ATR: < 10% (volatilité contrôlée)
- Volume adaptatif selon score (50k-200k USD)
- Price change: entre +1.5% et +15%
- Maximum 5 positions simultanées (forcé!)
- Cooldown 4h entre trades du même token

# Bonus: Volume spike avec score >= 65 peut override certains filtres
```

### Gestion des Positions (dans `paper_trader.py`)
```python
- Position size: 8% du portfolio max
- Stop-loss: DYNAMIQUE basé sur ATR (3% à 6%)
  - 2x ATR = stop-loss adaptatif à la volatilité
  - Fallback: 4% si ATR non disponible
- Take-profit échelonné:
  - TP1: +2% → vendre 25%
  - TP2: +5% → vendre 40%
  - TP3: +10% → tout vendre
- Trailing stop: 2.5% (activé à +1.5%)
- Timeout: fermeture auto après 12h si stagnant (<1%)
```

### Détection Momentum AVANCÉE (dans `momentum_detector.py`)
```python
# Indicateurs Techniques Complets:
- RSI (14 périodes) - Évite les surachats/surventes
- Stochastic RSI - Plus sensible que RSI standard
- MACD (12, 26, 9) - Confirmation de tendance
- EMA Crossover (9/21) - Détection de renversements
- ATR (14) - Mesure de volatilité pour SL dynamique
- Corrélation BTC - Trade avec le marché global

# Paramètres de détection:
- Volume spike multiplier: 1.5x
- Breakout threshold: 2%
- Min volume: $100,000
- Top gainers analysés: 50
- Score minimum: 55/100 (multi-facteurs)
```

### Score Multi-Facteurs (0-100 points)
```python
Base score                  : 50
+ Price change (sweet spot) : -5 à +10
+ Volume bonus              : 0 à +15
+ RSI adjustment            : -15 à +15
+ Stochastic RSI            : -10 à +10
+ MACD confirmation         : -15 à +15
+ EMA trend alignment       : -10 à +10
+ BTC correlation           : -15 à +15
+ Signal type bonus         : +5 à +10
- Volatility penalty        : 0 à -15
```

---

## 📊 MÉTRIQUES À SURVEILLER

Sur le dashboard (https://cryptobot-ultimate-production.up.railway.app/):

| Métrique | Objectif avant trading réel |
|----------|----------------------------|
| Win Rate | > 50% |
| Portfolio | Croissance stable |
| ML Samples | > 50 |
| Uptime | Stable 24/7 |

---

## 🚀 COMMANDES UTILES

### Déployer une mise à jour
```powershell
cd "c:\Users\plani\Documents\GANG\Nouveau dossier"
railway link   # Sélectionner: cryptobot-ultimate > production > cryptobot-ultimate
railway up
```

### Voir les logs en direct
```powershell
railway logs
```

### Lancer en local (test)
```powershell
python src/main.py --simulation
```

---

## 🔧 FICHIERS CLÉS À MODIFIER

### Pour changer la stratégie de trading:
- `src/core/orchestrator.py` → fonction `on_momentum_signal()`
- `src/trading/paper_trader.py` → paramètres TP/SL
- `src/modules/momentum_detector.py` → paramètres de détection

### Pour activer/désactiver des modules:
- Fichier `.env` → variables `ENABLE_*`

### Pour changer la configuration:
- `src/core/config.py` → classe `Settings`

---

## 📁 STRUCTURE DES DONNÉES

### Fichiers persistants (dans le container Railway):
- `data/paper_portfolio.json` → État du portfolio simulé
- `data/risk_state.json` → État du risk manager
- `cryptobot.db` → Base SQLite (trades, modèle ML)

### Variables d'environnement importantes:
```env
SIMULATION_MODE=True          # TOUJOURS True pour l'instant
BINANCE_API_KEY=xxx           # Clé API Binance
BINANCE_SECRET=xxx            # Secret API Binance
ENABLE_SNIPER=True            # Module sniper actif
ENABLE_NEWS_TRADER=True       # Module news actif
ENABLE_ML_PREDICTOR=True      # Module ML actif
```

---

## ⚠️ POINTS D'ATTENTION

### Ce qui fonctionne bien:
- ✅ Momentum detector trouve des signaux
- ✅ Paper trader exécute les trades
- ✅ ML model s'entraîne (toutes les 6h)
- ✅ Dashboard healthcheck accessible
- ✅ Déploiement Railway stable

### Ce qui est désactivé (pas prêt):
- ❌ Sentiment analyzer (Twitter API pas configurée)
- ❌ Arbitrage (nécessite plusieurs exchanges)
- ❌ DeFi optimizer (smart contracts pas déployés)
- ❌ Copy trading (pas de wallets à suivre)

### Risques connus:
- Le bot peut acheter "trop haut" si les paramètres sont mal réglés
- Le modèle ML a besoin de plus de données (>50 samples)
- Les positions peuvent être bloquées si le prix ne bouge pas

---

## 📈 HISTORIQUE DES AMÉLIORATIONS

### Décembre 2024 - v2.0 (Ultra Optimisé):

#### Phase 1: Smart Momentum
1. ✅ Stratégie "Smart Momentum" implémentée
   - Achat précoce (+1.5% à +12%)
   - Évite les pumps tardifs
   
2. ✅ Risk management ultra-serré
   - Stop-loss: 4%
   - Trailing stop: 2.5% (activé à +1.5%)
   - Take-profits: +2%, +5%, +10%
   - Timeout: 12h pour positions stagnantes
   
3. ✅ Limite positions stricte (max 5)
   - Fermeture forcée des excédentaires
   - Les pires positions fermées en premier

#### Phase 2: Technical Analysis Complete
4. ✅ Module Indicateurs Techniques (`src/utils/indicators.py`)
   - RSI (14 périodes)
   - Stochastic RSI (plus sensible)
   - MACD (12, 26, 9) avec signal line
   - EMA Crossover (9/21) - Golden/Death Cross
   - ATR (Average True Range) pour volatilité
   - Bollinger Bands

5. ✅ Corrélation BTC
   - Fetch du trend BTC toutes les 5 min
   - Skip trades si BTC strong bearish
   - Bonus score si aligné avec BTC

6. ✅ Score Multi-Facteurs (0-100)
   - Combine tous les indicateurs
   - Score minimum: 55/100 pour trader
   - Logs détaillés avec emoji couleur

7. ✅ Stop-Loss Dynamique basé sur ATR
   - 2x ATR = stop-loss adaptatif
   - Min 3%, Max 6%
   - S'adapte à la volatilité du token

8. ✅ LunarCrush désactivé (API cassée)

---

## 🎯 PROCHAINES ÉTAPES

1. **Court terme (1-2 semaines)**
   - Surveiller le PnL réalisé (pas latent)
   - Vérifier que TP1 est atteint à +2%
   - Confirmer fermeture des positions stagnantes

2. **Moyen terme (1-2 mois)**
   - Atteindre win rate > 55%
   - Portfolio virtuel en croissance stable
   - Valider la stratégie sur 100+ trades

3. **Long terme (après validation)**
   - Passer en mode réel avec $50-100
   - Augmenter progressivement le capital
   - Activer les modules avancés (ML)

---

## 🆘 EN CAS DE PROBLÈME

### Le bot ne répond plus:
1. Vérifier Railway dashboard
2. Regarder les logs: `railway logs`
3. Redéployer: `railway up`

### Le bot perd de l'argent:
1. C'est normal au début (simulation)
2. Analyser les trades perdants
3. Ajuster les paramètres dans `orchestrator.py`

### Erreur de déploiement:
1. Vérifier que le code compile: `python -m py_compile src/main.py`
2. Vérifier les dépendances: `pip install -r requirements.txt`
3. Consulter les logs de build sur Railway

---

## 📞 RAPPEL IMPORTANT

**CE BOT EST EN MODE SIMULATION**

- Aucun argent réel n'est utilisé
- Les profits/pertes sont virtuels
- Ne JAMAIS passer en mode réel sans validation complète (60-90 jours)
- Quand prêt: modifier `SIMULATION_MODE=False` dans `.env` sur Railway

---

*Dernière mise à jour: 21 décembre 2024 - v2.0 Ultra Technical Analysis*
