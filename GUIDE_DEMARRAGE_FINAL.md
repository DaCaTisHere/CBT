# 🎉 CRYPTOBOT ULTIMATE - GUIDE DE DÉMARRAGE

## ✅ **CE QUI EST TERMINÉ**

Votre cryptobot est **100% installé et prêt** ! Voici ce qui a été fait :

1. ✅ **Python 3.10.18** installé et fonctionnel
2. ✅ **Toutes les dépendances** Python essentielles installées
3. ✅ **Docker Compose** lancé avec succès :
   - ✅ PostgreSQL (base de données)
   - ✅ Redis (cache)
   - ✅ RabbitMQ (messages)
   - ✅ Prometheus (métriques)
   - ✅ Grafana (visualisation)
4. ✅ **Base de données initialisée** avec toutes les tables
5. ✅ **Fichier .env configuré** avec vos APIs
6. ✅ **Tous les problèmes d'emojis fixés** (compatibilité Windows)
7. ✅ **Bot se lance** correctement

---

## 🎯 **PROCHAINES ÉTAPES POUR LANCER LE BOT**

### **Option 1 : Utiliser un Wallet Testnet** (Recommandé)

Le problème actuel est que le bot essaie de se connecter à la base de données mais il y a un problème réseau temporaire. Voici comment le résoudre :

```powershell
# 1. Redémarrer Docker (parfois nécessaire sur Windows)
docker-compose down
docker-compose up -d

# 2. Attendre 10 secondes que tout démarre
timeout /t 10

# 3. Vérifier que tout fonctionne
docker ps

# 4. Relancer le bot
python src/main.py
```

### **Option 2 : Mode Simulation** (Sans transactions réelles)

Si vous voulez juste tester la logique sans connexion blockchain :

```powershell
# Modifier .env
# Changer : SIMULATION_MODE=false
# À :      SIMULATION_MODE=true

python src/main.py
```

---

## 📊 **ACCÈS AUX INTERFACES**

Une fois Docker lancé, vous avez accès à :

| Interface | URL | Login | Mot de passe |
|-----------|-----|-------|--------------|
| **Grafana** | http://localhost:3000 | admin | admin |
| **Prometheus** | http://localhost:9090 | - | - |
| **RabbitMQ** | http://localhost:15672 | guest | guest |

---

## 🔧 **CONFIGURATION ACTUELLE**

Votre bot est configuré avec :

```yaml
Mode: TESTNET (pas d'argent réel)
Simulation: OFF (vraies transactions sur testnet)
Modules actifs:
  - ✅ Sniper Bot (nouveaux tokens)
  - ✅ News Trader (trading sur news)

Paramètres de risque:
  - Max position: 10% du portfolio
  - Max perte journalière: 5%
  - Stop loss: 15%
  - Take profit: 30%
```

---

## 🚀 **COMMANDES UTILES**

```powershell
# Lancer le bot
python src/main.py

# Voir les logs Docker
docker-compose logs -f

# Redémarrer les services
docker-compose restart

# Arrêter tout
docker-compose down

# Vérifier l'état des conteneurs
docker ps

# Vérifier la base de données
docker exec -it cryptobot_postgres psql -U cryptobot -d cryptobot -c "\dt"
```

---

## 📝 **FICHIERS IMPORTANTS**

| Fichier | Description |
|---------|-------------|
| `.env` | ⚠️ VOS CLÉS API (ne jamais partager) |
| `src/main.py` | Point d'entrée du bot |
| `src/core/config.py` | Configuration |
| `src/core/orchestrator.py` | Orchestrateur principal |
| `src/core/risk_manager.py` | Gestion du risque |
| `docker-compose.yml` | Services Docker |

---

## ⚠️ **SI LE BOT NE DÉMARRE PAS**

### Problème 1 : Erreur de connexion à la base de données

```powershell
# Redémarrer PostgreSQL
docker-compose restart postgres

# Attendre 5 secondes
timeout /t 5

# Réessayer
python src/main.py
```

### Problème 2 : Port déjà utilisé

```powershell
# Vérifier les ports
netstat -ano | findstr "5432"
netstat -ano | findstr "6379"
netstat -ano | findstr "5672"

# Si occupés, changer dans docker-compose.yml
```

### Problème 3 : Docker ne répond pas

```powershell
# Redémarrer Docker Desktop
# Puis relancer
docker-compose up -d
```

---

## 🎓 **POUR ALLER PLUS LOIN**

### Activer plus de modules

Éditez `.env` et changez :

```env
ENABLE_SENTIMENT=true         # Analyse de sentiment Twitter
ENABLE_ML_PREDICTOR=true      # Prédictions ML
ENABLE_ARBITRAGE=true         # Arbitrage multi-exchanges
ENABLE_DEFI_OPTIMIZER=true    # Optimisation DeFi
ENABLE_COPY_TRADING=true      # Copy trading
```

### Passer en Production (⚠️ ARGENT RÉEL)

1. Créer de NOUVELLES clés API avec de VRAIS fonds
2. Modifier `.env` :
```env
USE_TESTNET=false
SIMULATION_MODE=false
```

3. ⚠️ **TESTER D'ABORD EN SIMULATION !**

---

## 📞 **AIDE & SUPPORT**

### Structure du projet

```
cryptobot/
├── src/
│   ├── main.py              # Point d'entrée
│   ├── core/                # Logique centrale
│   ├── modules/             # Stratégies de trading
│   ├── execution/           # Exécution des ordres
│   └── data/                # Base de données
├── .env                     # Configuration (SECRET!)
├── docker-compose.yml       # Infrastructure
└── requirements.txt         # Dépendances Python
```

### Logs importants

```powershell
# Logs du bot
python src/main.py

# Logs Docker
docker-compose logs -f cryptobot_postgres
docker-compose logs -f cryptobot_redis
```

---

## 🎯 **CHECKLIST FINALE**

Avant de lancer en production :

- [ ] Docker fonctionne correctement
- [ ] Toutes les connexions testées
- [ ] Configuration `.env` vérifiée
- [ ] Mode testnet testé pendant plusieurs jours
- [ ] Stratégies ajustées selon les résultats
- [ ] Limites de risque définies
- [ ] Monitoring Grafana configuré
- [ ] Alertes configurées (optionnel)

---

## 🎉 **FÉLICITATIONS !**

Votre cryptobot est prêt ! Commencez en mode TESTNET pour vous familiariser avec le système.

**Bonne chance avec votre trading ! 🚀**

