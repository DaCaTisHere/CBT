# 📖 GUIDE COMPLET D'UTILISATION - CRYPTOBOT ULTIMATE

**Pour:** Utilisateur débutant à avancé  
**Temps de lecture:** 15 minutes  
**Temps de setup:** 30-60 minutes

---

## 🎯 COMMENT FONCTIONNE LE BOT ?

### Vue d'ensemble Simple

```
┌─────────────────────────────────────────────────────────────┐
│  VOUS DÉMARREZ LE BOT                                       │
│  python src/main.py                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ORCHESTRATEUR CENTRAL démarre                              │
│  • Lit votre configuration (.env)                           │
│  • Connecte à la blockchain (Ethereum, BSC, etc.)          │
│  • Connecte aux exchanges (Binance, Coinbase, etc.)        │
│  • Initialise les 7 modules de trading                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  7 MODULES DE TRADING s'exécutent en parallèle:            │
│                                                             │
│  1. 🎯 SNIPER BOT                                           │
│     → Surveille nouveaux tokens sur DEX (Uniswap, etc.)   │
│     → Achète instantanément si safe                        │
│     → Vend avec profit (x2, x5, x10+)                      │
│                                                             │
│  2. 📢 NEWS TRADER                                          │
│     → Surveille annonces Binance/Coinbase                  │
│     → Achète dès qu'un listing est annoncé                 │
│     → Vend quand le prix monte (+20-100%)                  │
│                                                             │
│  3. 🧠 SENTIMENT ANALYZER                                   │
│     → Analyse Twitter, Reddit, Telegram                    │
│     → Détecte hype ou panique                              │
│     → Trade selon sentiment dominant                        │
│                                                             │
│  4. 🤖 ML PREDICTOR                                         │
│     → Utilise IA pour prédire prix futurs                  │
│     → Modèles LSTM, XGBoost entraînés                      │
│     → Trade selon prédictions                               │
│                                                             │
│  5. ⚡ ARBITRAGE                                            │
│     → Compare prix entre exchanges                          │
│     → Achète sur exchange A, vend sur B                    │
│     → Profit sur différence de prix                         │
│                                                             │
│  6. 🌾 DEFI OPTIMIZER                                       │
│     → Trouve meilleurs rendements DeFi                      │
│     → Auto-compound intérêts                                │
│     → Déplace fonds vers meilleures pools                   │
│                                                             │
│  7. 👤 COPY TRADING                                         │
│     → Suit portefeuilles de traders experts                │
│     → Copie leurs trades en temps réel                     │
│     → Profite de leur expertise                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  RISK MANAGER surveille TOUT                                │
│  • Vérifie chaque trade avant exécution                    │
│  • Stop-loss automatique si perte                          │
│  • Arrête trading si perte journalière > 5%                │
│  • Protège votre capital                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  RÉSULTATS                                                  │
│  • Trades affichés en temps réel dans console              │
│  • Statistiques sauvegardées en base de données            │
│  • Alertes Telegram (si configuré)                         │
│  • Dashboard Grafana (http://localhost:3000)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 OÙ METTRE VOTRE WALLET ET VOS CLÉS ?

### Étape 1: Créer le Fichier de Configuration

**Sur Windows:**
```powershell
# 1. Copier le template
Copy-Item ENV_EXAMPLE.txt .env

# 2. Ouvrir avec Notepad
notepad .env
```

**Sur Linux/Mac:**
```bash
# 1. Copier le template
cp ENV_EXAMPLE.txt .env

# 2. Ouvrir avec votre éditeur
nano .env
# ou
code .env  # Si vous avez VSCode
```

### Étape 2: Remplir les Informations Critiques

Ouvrez le fichier `.env` et remplissez **ces sections obligatoires** :

#### 🔑 Section 1: Clé RPC Ethereum

```bash
# Obtenez une clé GRATUITE sur https://www.alchemy.com/
# 1. Créez un compte
# 2. Créez une app "Ethereum Mainnet"
# 3. Copiez la clé API

ETHEREUM_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/COLLEZ_VOTRE_CLE_ICI
```

**Pourquoi ?** Le bot a besoin de communiquer avec la blockchain Ethereum.

#### 💼 Section 2: Votre Wallet (⚠️ CRITIQUE !)

```bash
# ⚠️ UTILISEZ UN WALLET TESTNET POUR DÉBUTER !
# Pas votre wallet principal avec de l'argent réel !

# Votre clé privée
WALLET_PRIVATE_KEY=0x1234567890abcdef...  # Votre vraie clé

# Votre adresse (optionnel, calculée automatiquement)
WALLET_ADDRESS=0xVotreAdresse...
```

**Comment obtenir un wallet testnet ?**

1. **Avec MetaMask:**
   - Ouvrez MetaMask
   - En haut: Cliquez "Ethereum Mainnet" → "Goerli test network"
   - Créez un nouveau compte (Account 2 par exemple)
   - Cliquez les 3 points → Account details → Export Private Key
   - ⚠️ **C'est CETTE clé** que vous mettez dans WALLET_PRIVATE_KEY

2. **Obtenir des tokens testnet gratuits:**
   - Allez sur https://goerlifaucet.com/
   - Collez votre adresse
   - Recevez des ETH testnet gratuits
   - Pas d'argent réel = Pas de risque !

#### 💱 Section 3: API Binance (Optionnel pour commencer)

```bash
# Seulement si vous voulez trader sur Binance
BINANCE_API_KEY=votre_cle
BINANCE_SECRET=votre_secret
```

**Comment obtenir ?**
1. https://www.binance.com/en/my/settings/api-management
2. Créer nouvelle clé API
3. ⚠️ **Activer SEULEMENT "Enable Reading"** et "Enable Spot & Margin Trading"
4. **NE PAS activer "Enable Withdrawals"** (sécurité)

#### ⚠️ Section 4: Mode de Fonctionnement

```bash
# POUR DÉBUTER (pas d'argent réel)
USE_TESTNET=true
SIMULATION_MODE=false
DRY_RUN=false

# Mode simulation (aucune transaction)
# USE_TESTNET=true
# SIMULATION_MODE=true

# Mode production (⚠️ argent réel !)
# USE_TESTNET=false
# SIMULATION_MODE=false
```

**Modes disponibles:**
- `USE_TESTNET=true` → Utilise testnets (Goerli, BSC Testnet) - **RECOMMANDÉ**
- `SIMULATION_MODE=true` → Simule tout, aucune vraie transaction
- `DRY_RUN=true` → Log les trades mais ne les exécute pas

---

## 🚀 INSTALLATION COMPLÈTE (Étape par Étape)

### Prérequis

**À installer d'abord:**
1. **Python 3.11+** → https://www.python.org/downloads/
2. **Docker Desktop** → https://www.docker.com/products/docker-desktop/
3. **Git** (optionnel) → https://git-scm.com/downloads

---

### Installation sur Windows (PowerShell)

```powershell
# 1. Aller dans le dossier du projet
cd "C:\Users\plani\Documents\GANG\Nouveau dossier"

# 2. Créer environnement virtuel Python
python -m venv venv

# 3. Activer l'environnement
venv\Scripts\activate

# 4. Mettre à jour pip
python -m pip install --upgrade pip

# 5. Installer toutes les dépendances
pip install -r requirements.txt

# 6. Créer le fichier .env
Copy-Item ENV_EXAMPLE.txt .env
notepad .env
# → Remplir avec vos clés (voir section précédente)

# 7. Démarrer les services Docker
docker-compose up -d

# 8. Attendre que les services démarrent (30 secondes)
timeout /t 30

# 9. Vérifier que tout fonctionne
python scripts/test_connections.py
```

---

### Installation sur Linux/Mac (Terminal)

```bash
# 1. Aller dans le dossier
cd ~/Documents/cryptobot-ultimate

# 2. Créer environnement virtuel
python3 -m venv venv

# 3. Activer
source venv/bin/activate

# 4. Mettre à jour pip
pip install --upgrade pip

# 5. Installer dépendances
pip install -r requirements.txt

# 6. Créer .env
cp ENV_EXAMPLE.txt .env
nano .env  # ou vim .env
# → Remplir avec vos clés

# 7. Démarrer Docker
docker-compose up -d

# 8. Attendre
sleep 30

# 9. Tester
python scripts/test_connections.py
```

---

## 🎮 DÉMARRER LE BOT

### Mode 1: Simulation Pure (Recommandé pour débuter)

```bash
python src/main.py --simulation
```

**Ce qui se passe:**
- ✅ Aucune transaction réelle
- ✅ Simule détection de tokens, news, etc.
- ✅ Log tous les trades "simulés"
- ✅ Parfait pour tester que tout fonctionne

### Mode 2: Testnet (Tokens gratuits)

```bash
# 1. Configurer .env
USE_TESTNET=true
SIMULATION_MODE=false

# 2. Obtenir tokens testnet
# Goerli faucet: https://goerlifaucet.com/
# BSC testnet faucet: https://testnet.binance.org/faucet-smart

# 3. Lancer
python src/main.py --testnet
```

**Ce qui se passe:**
- ✅ Vraies transactions sur testnet
- ✅ Tokens gratuits (pas d'argent réel)
- ✅ Test réaliste du bot
- ✅ Voir si stratégies fonctionnent

### Mode 3: Production (⚠️ Argent Réel)

```bash
# 1. Configurer .env
USE_TESTNET=false
SIMULATION_MODE=false

# 2. ⚠️ Commencer avec petit capital ($100-500)

# 3. Confirmer
python src/main.py

# Le bot demandera confirmation:
# "PRODUCTION MODE with REAL MONEY. Continue? (yes/no):"
```

---

## 📊 SURVEILLER LE BOT

### Console (Terminal)

Quand le bot tourne, vous verrez:

```
🤖 CRYPTOBOT ULTIMATE v0.1.0 🤖
====================================

📋 Configuration:
   Environment: development
   Testnet: True
   Simulation: False

🎯 Enabled Modules:
   ✅ Sniper Bot
   ✅ News Trader

🚀 Starting Cryptobot Ultimate...
✅ Database connected
✅ Risk manager initialized
✅ Wallet Manager initialized
   Address: 0x1234...5678
   Balance: 1.5 ETH

▶️  Sniper Bot started - monitoring for new tokens...
▶️  News Trader started - monitoring announcements...

🔔 New token detected: 0xABC...DEF
⚠️  Token rejected: Safety score too low

🔔 LISTING ANNOUNCEMENT: BTC on binance
✅ Order executed: 12345 | BUY 100 BTC/USDT
```

### Dashboard Grafana

1. Ouvrir navigateur: http://localhost:3000
2. Login: `admin` / `admin`
3. Dashboards disponibles:
   - Portfolio Overview
   - Trading Activity
   - System Health

### Logs Fichiers

Les logs sont sauvegardés dans:
```
logs/cryptobot.log
```

---

## ⚙️ CONFIGURATION AVANCÉE

### Ajuster le Risk Management

Dans `.env`:

```bash
# Taille maximale par trade (% du portfolio)
MAX_POSITION_SIZE_PCT=10.0  # 10% max par trade

# Perte maximale journalière (%)
MAX_DAILY_LOSS_PCT=5.0  # Stop si -5% sur la journée

# Stop-loss par défaut (%)
STOP_LOSS_PCT=15.0  # Vendre si -15%

# Take-profit par défaut (%)
TAKE_PROFIT_PCT=30.0  # Vendre si +30%
```

**Exemples de profils:**

**Conservateur:**
```bash
MAX_POSITION_SIZE_PCT=5.0
MAX_DAILY_LOSS_PCT=3.0
STOP_LOSS_PCT=10.0
TAKE_PROFIT_PCT=20.0
```

**Équilibré (recommandé):**
```bash
MAX_POSITION_SIZE_PCT=10.0
MAX_DAILY_LOSS_PCT=5.0
STOP_LOSS_PCT=15.0
TAKE_PROFIT_PCT=30.0
```

**Agressif (⚠️ risqué):**
```bash
MAX_POSITION_SIZE_PCT=20.0
MAX_DAILY_LOSS_PCT=10.0
STOP_LOSS_PCT=20.0
TAKE_PROFIT_PCT=50.0
```

### Activer/Désactiver Modules

Dans `.env`:

```bash
# Modules prioritaires (commencez avec ceux-ci)
ENABLE_SNIPER=true
ENABLE_NEWS_TRADER=true

# Modules avancés (activez après tests)
ENABLE_SENTIMENT=false
ENABLE_ML_PREDICTOR=false
ENABLE_ARBITRAGE=false
ENABLE_DEFI_OPTIMIZER=false
ENABLE_COPY_TRADING=false
```

---

## 🛑 ARRÊTER LE BOT

### Arrêt Gracieux

Dans le terminal où le bot tourne:
```
Ctrl + C
```

Le bot va:
1. Fermer positions ouvertes
2. Sauvegarder état
3. Déconnecter proprement
4. Afficher statistiques finales

### Arrêt d'Urgence

Si le bot ne répond plus:
```bash
# Trouver le processus
ps aux | grep python

# Tuer le processus
kill -9 <PID>

# Ou sur Windows
taskkill /F /IM python.exe
```

---

## 🐛 PROBLÈMES FRÉQUENTS

### Problème: "Database connection failed"

**Solution:**
```bash
# Vérifier que Docker est lancé
docker-compose ps

# Redémarrer PostgreSQL
docker-compose restart postgres

# Vérifier logs
docker-compose logs postgres
```

### Problème: "Invalid RPC URL"

**Solution:**
1. Vérifier que vous avez une clé Alchemy valide
2. Tester l'URL manuellement:
```bash
curl https://eth-mainnet.alchemyapi.io/v2/VOTRE_CLE \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### Problème: "ModuleNotFoundError"

**Solution:**
```bash
# Réinstaller dépendances
pip install -r requirements.txt --force-reinstall

# Vérifier que venv est activé
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### Problème: Pas de tokens testnet

**Solution:**
1. Aller sur https://goerlifaucet.com/
2. Coller votre adresse wallet
3. Attendre 1-2 minutes
4. Vérifier balance:
```bash
python scripts/test_connections.py
```

---

## 📈 WORKFLOW RECOMMANDÉ

### Jour 1: Setup & Tests
1. ✅ Installation complète
2. ✅ Configuration .env
3. ✅ Lancer en mode simulation (24h)
4. ✅ Observer comportement

### Jour 2-3: Testnet
1. ✅ Obtenir tokens testnet
2. ✅ Lancer en mode testnet
3. ✅ Premiers vrais trades (testnet)
4. ✅ Analyser résultats

### Semaine 1: Optimisation
1. ✅ Ajuster risk management
2. ✅ Tester différentes configs
3. ✅ Monitorer performances
4. ✅ Lire logs et comprendre

### Semaine 2+: Production (si prêt)
1. ✅ Commencer avec $100-500
2. ✅ Monitoring 24/7
3. ✅ Ajustements quotidiens
4. ✅ Scaler progressivement

---

## 🔐 SÉCURITÉ - CHECKLIST

Avant production:
- [ ] `.env` n'est PAS dans Git
- [ ] Wallet testnet utilisé pour tests
- [ ] Clés API Binance sans "Enable Withdrawals"
- [ ] Backup clé privée dans endroit sûr
- [ ] 2FA activé sur tous comptes
- [ ] Petit capital initial ($100-500)
- [ ] Stop-loss activés et testés
- [ ] Alertes configurées

---

## 📞 AIDE & SUPPORT

**Documentation:**
- `README.md` - Vue d'ensemble
- `DEPLOYMENT_GUIDE.md` - Déploiement
- `TECH_STACK_DETAILED.md` - Détails techniques

**Fichiers de configuration:**
- `.env` - Votre configuration (à créer)
- `ENV_EXAMPLE.txt` - Template

**En cas de problème:**
1. Lire les logs: `logs/cryptobot.log`
2. Vérifier Docker: `docker-compose logs`
3. Tester connexions: `python scripts/test_connections.py`

---

## ✅ RÉSUMÉ RAPIDE

### Pour Démarrer en 5 Minutes

```bash
# 1. Créer .env
Copy-Item ENV_EXAMPLE.txt .env

# 2. Remplir .env (minimum)
ETHEREUM_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/VOTRE_CLE
WALLET_PRIVATE_KEY=votre_cle_testnet
USE_TESTNET=true

# 3. Installer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 4. Docker
docker-compose up -d

# 5. Lancer
python src/main.py --simulation
```

---

**Voilà ! Vous savez TOUT maintenant ! 🚀**

Le bot est prêt à fonctionner dès que vous mettez vos clés dans `.env` !

