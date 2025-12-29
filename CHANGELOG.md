# 📝 CHANGELOG - CRYPTOBOT ULTIMATE

## [3.0.0] - 2025-12-29 - CORRECTIFS ULTRA-STRICTS

### 🚨 Problèmes Identifiés
- **Win rate catastrophique**: 27.4% (1224 losses vs 461 wins)
- **Sur-trading massif**: 1685 trades en 113h = 14.9 trades/heure
- **ML non fonctionnel**: Seulement 21 trades analysés (1.25%), 0% learned win rate
- **TP trop agressif**: Vend 25% dès +1.5%, coupe les winners trop tôt

### ✅ Solutions Implémentées

#### 1. Momentum Detector - Réduction 90% du trading
- `MIN_ADVANCED_SCORE`: 55 → **80** (+45%)
- `MIN_VOLUME_USD`: $100k → **$500k** (+400%)
- `VOLUME_SPIKE_MULTIPLIER`: 1.5 → **3.0** (+100%)
- `TOKEN_COOLDOWN_HOURS`: 4 → **8** (+100%)
- `MAX_VOLATILITY_24H`: 25% → **15%** (-40%)
- `RSI_OVERBOUGHT`: 75 → **70**
- `RSI_NEUTRAL_HIGH`: 65 → **60**
- `TOP_GAINERS_COUNT`: 50 → **20** (-60%)

**Scoring System**:
- Score base: 50 → **40** points (plus strict)
- Pénalités RSI: -15 → **-20** (plus sévères)
- Pénalités StochRSI: -10 → **-15**
- Pénalités MACD: -15 → **-20**
- Pénalités EMA: -10 → **-15**
- Pénalités BTC: -15 → **-20**
- Pénalités Volatilité: -15 → **-20**, seuils abaissés (20→15, 15→12, 10→8)

#### 2. Orchestrator - Filtres Ultra-Stricts
- `MIN_SCORE`: 65 → **80** (+23%)
- Volume adaptatif selon score:
  - Score ≥85: $200k min
  - Score ≥80: $400k min
  - Sinon: $500k min
- `RSI`: 25-70 → **30-65**
- `StochRSI`: ≤80 → **≤70**
- `Change percent`: 1.5-15% → **2-12%**
- `ATR`: ≤10% → **≤8%**
- `BTC correlation`: ≥0 → **>0** (strict positif)
- `MACD`: "!= bearish" → **"in [bullish, neutral]"**
- `EMA`: "not bearish" → **"in [bullish, bullish_cross, neutral]"**
- Volume spike score: ≥70 → **≥75**
- `ML_CONFIDENCE_THRESHOLD`: implicite 0.55 → **0.65**

#### 3. Paper Trader - SL/TP Optimisés
- `default_stop_loss`: 4% → **3%**
- `trailing_stop_pct`: 2.5% → **2%**
- `trailing_activated`: +1.5% → **+2%** (laisser respirer)
- `TP1`: +1.5% (sell 25%) → **+3% (sell 20%)**
- `TP2`: +4% (sell 40%) → **+6% (sell 30%)**
- `TP3`: +8% → **+10%**
- `Timeout`: 6h → **4h** (capital libéré plus vite)

#### 4. Auto Learner - Corrections ML
- **Validation exits**: Warning si pas d'entry trouvée
- **Force training**: Si ≥20 completed trades au démarrage
- **Thresholds adaptatifs**:
  - ≥100 trades: threshold 0.65
  - ≥50 trades: threshold 0.60
  - <50 trades: threshold 0.55
- **Logging amélioré**: ✅ pour exits réussis, ⚠️ pour problèmes

### 🎯 Objectifs Visés
| Métrique | Avant | Cible |
|----------|-------|-------|
| Trades/heure | 14.9 | **1-2** (-90%) |
| Win Rate | 27.4% | **50%+** (+23%) |
| ML Coverage | 1.25% | **100%** |
| Avg Win | ? | **+5-8%** |
| Avg Loss | ? | **-2-3%** |

### 📝 Fichiers Modifiés
- `src/modules/momentum_detector.py`
- `src/core/orchestrator.py`
- `src/trading/paper_trader.py`
- `src/ml/auto_learner.py`
- `RELANCE/CONTEXTE_PROJET.md`
- `ANALYSE_CRITIQUE_BOT.md` (nouveau)

### 🚀 Déploiement
- Railway project: cryptobot-ultimate
- Environment: production
- Build time: ~78s
- Dashboard: https://cryptobot-ultimate-production.up.railway.app/

---

## [2.0.0] - 2025-12-28 - Auto-Learning System

### Added
- Machine Learning auto-learning system
- Automatic data collection for every trade
- Periodic model retraining (every 6 hours)
- ML-based trade filtering

### Changed
- Momentum detector scoring improved
- Risk management optimized

---

## [1.0.0] - 2025-12-27 - Initial Release

### Added
- Momentum detection system
- Paper trading engine
- Technical indicators (RSI, MACD, EMA, Stochastic RSI, ATR)
- BTC correlation analysis
- Trailing stop-loss
- Scaled take-profits
- Telegram notifications
- Railway deployment
- Healthcheck dashboard
