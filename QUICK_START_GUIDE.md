# 🚀 QUICK START GUIDE - CRYPTOBOT ULTIMATE

**Pour:** Démarrage rapide du projet  
**Temps estimé:** 2-4 heures pour setup complet  
**Niveau:** Intermédiaire à Avancé

---

## 📋 PRÉREQUIS

### Connaissances Requises
- ✅ Python (niveau intermédiaire+)
- ✅ Docker & containers
- ✅ Git & GitHub
- ✅ Bases blockchain (transactions, wallets)
- ✅ APIs REST
- ✅ Linux/Unix command line

### Outils Nécessaires
```bash
# Vérifier versions
python --version  # 3.11+
docker --version  # 20.10+
git --version     # 2.30+
node --version    # 18+ (optionnel)
```

### Capital & Comptes
- **Capital test:** $500-1000 minimum (pour tests mainnet)
- **Binance account** (avec API keys)
- **Alchemy account** (RPC Ethereum gratuit)
- **GitHub account**

---

## ⚡ INSTALLATION RAPIDE (30 minutes)

### Option 1: Setup Local (Développement)

```bash
# 1. Clone repository (à créer d'abord!)
git clone https://github.com/your-username/cryptobot-ultimate.git
cd cryptobot-ultimate

# 2. Virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Éditer .env avec vos clés (voir section Configuration)

# 5. Start services
docker-compose up -d

# 6. Vérifier services
docker-compose ps
# Doit afficher: postgres, redis, rabbitmq (tous "Up")

# 7. Initialize database
alembic upgrade head

# 8. Test connection
python scripts/test_connections.py

# 9. (Optionnel) Load sample data
python scripts/load_sample_data.py

# 10. Start bot (mode test)
python src/main.py --mode test --testnet
```

**✅ Si tout fonctionne:**
- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- RabbitMQ UI: http://localhost:15672 (guest/guest)

---

### Option 2: Docker Only (Minimal)

```bash
# Clone repo
git clone https://github.com/your-username/cryptobot-ultimate.git
cd cryptobot-ultimate

# Setup env
cp .env.example .env
# Éditer .env

# Start everything with Docker
docker-compose -f docker-compose.full.yml up -d

# Check logs
docker-compose logs -f cryptobot-core
```

---

## 🔧 CONFIGURATION MINIMALE

### .env (Critical Variables)

```bash
# ==========================================
# BLOCKCHAIN RPCs (REQUIRED)
# ==========================================

# Ethereum (Get free key: https://alchemy.com)
ETHEREUM_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/YOUR_KEY
ETHEREUM_TESTNET_RPC_URL=https://eth-goerli.alchemyapi.io/v2/YOUR_KEY

# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_TESTNET_RPC_URL=https://api.devnet.solana.com

# BSC
BSC_RPC_URL=https://bsc-dataseed.binance.org/
BSC_TESTNET_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545/

# ==========================================
# EXCHANGE APIs (REQUIRED for arbitrage)
# ==========================================

# Binance (Get keys: https://www.binance.com/en/my/settings/api-management)
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET=your_secret_here

# Coinbase (Optionnel mais recommandé)
COINBASE_API_KEY=
COINBASE_SECRET=

# ==========================================
# WALLET (⚠️ ULTRA IMPORTANT ⚠️)
# ==========================================

# NEVER commit this to Git!
# Use throwaway wallet for tests
WALLET_PRIVATE_KEY=0x... # Your private key (testnet pour commencer!)
WALLET_ADDRESS=0x...      # Corresponding address

# ==========================================
# DATABASE (Default Docker values)
# ==========================================

DATABASE_URL=postgresql://cryptobot:cryptobot@localhost:5432/cryptobot
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# ==========================================
# RISK MANAGEMENT (CRITICAL!)
# ==========================================

MAX_POSITION_SIZE_PCT=10        # Max 10% portfolio per trade
MAX_DAILY_LOSS_PCT=5            # Stop trading if -5% today
STOP_LOSS_PCT=15                # Default stop-loss
TAKE_PROFIT_PCT=30              # Default take-profit
MAX_SLIPPAGE_PCT=2              # Max slippage tolerated

# ==========================================
# FEATURES FLAGS (Enable/Disable modules)
# ==========================================

ENABLE_SNIPER=true
ENABLE_NEWS_TRADER=true
ENABLE_SENTIMENT=false          # Pas encore développé
ENABLE_ML_PREDICTOR=false       # Pas encore développé
ENABLE_ARBITRAGE=false          # Pas encore développé
ENABLE_DEFI_OPTIMIZER=false     # Pas encore développé
ENABLE_COPY_TRADING=false       # Pas encore développé

# ==========================================
# MONITORING (Optionnel initial)
# ==========================================

SENTRY_DSN=                     # Pour error tracking
TELEGRAM_BOT_TOKEN=             # Pour alertes
TELEGRAM_CHAT_ID=

# ==========================================
# ENVIRONMENT
# ==========================================

ENVIRONMENT=development         # development / staging / production
LOG_LEVEL=INFO                  # DEBUG / INFO / WARNING / ERROR
```

---

## 🧪 TESTS DE VÉRIFICATION

### 1. Test Connexions

Créer `scripts/test_connections.py`:

```python
#!/usr/bin/env python3
"""Test all critical connections"""

import asyncio
from web3 import Web3
from sqlalchemy import create_engine
import redis
import ccxt
from dotenv import load_dotenv
import os

load_dotenv()

async def test_all():
    print("🔍 Testing connections...\n")
    
    # 1. Ethereum RPC
    print("1️⃣ Testing Ethereum RPC...")
    try:
        w3 = Web3(Web3.HTTPProvider(os.getenv('ETHEREUM_RPC_URL')))
        block = w3.eth.block_number
        print(f"   ✅ Ethereum: Connected! Block: {block}")
    except Exception as e:
        print(f"   ❌ Ethereum: Failed - {e}")
    
    # 2. Database
    print("\n2️⃣ Testing PostgreSQL...")
    try:
        engine = create_engine(os.getenv('DATABASE_URL'))
        conn = engine.connect()
        print(f"   ✅ PostgreSQL: Connected!")
        conn.close()
    except Exception as e:
        print(f"   ❌ PostgreSQL: Failed - {e}")
    
    # 3. Redis
    print("\n3️⃣ Testing Redis...")
    try:
        r = redis.from_url(os.getenv('REDIS_URL'))
        r.ping()
        print(f"   ✅ Redis: Connected!")
    except Exception as e:
        print(f"   ❌ Redis: Failed - {e}")
    
    # 4. Binance API
    print("\n4️⃣ Testing Binance API...")
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
        })
        balance = exchange.fetch_balance()
        print(f"   ✅ Binance: Connected!")
    except Exception as e:
        print(f"   ❌ Binance: Failed - {e}")
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_all())
```

**Run:**
```bash
python scripts/test_connections.py
```

**Expected output:** Tous ✅

---

### 2. Test Premier Trade (Testnet)

```bash
# Mode simulation (pas de vraies transactions)
python src/main.py --mode simulation --duration 60

# Observer logs:
# - Prix fetched
# - Signaux détectés
# - Trades simulés
```

---

## 📚 STRUCTURE PROJET (Référence Rapide)

```
cryptobot-ultimate/
│
├── 📄 docs/                    # Documentation
│   ├── CRYPTOBOT_MASTER_PLAN.md
│   ├── TECH_STACK_DETAILED.md
│   └── ROADMAP_EXECUTION.md
│
├── 💻 src/                     # Code source
│   ├── core/                   # Orchestrateur
│   ├── modules/                # 7 stratégies
│   ├── data/                   # Data layer
│   ├── execution/              # Trading execution
│   └── utils/                  # Helpers
│
├── 🧪 tests/                   # Tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── 🐳 docker/                  # Docker configs
│   ├── Dockerfile.core
│   └── Dockerfile.sniper
│
├── 📊 infrastructure/          # IaC
│   ├── terraform/
│   └── k8s/
│
├── 📜 scripts/                 # Utility scripts
│   ├── setup.sh
│   ├── test_connections.py
│   └── load_data.py
│
├── .env.example                # Template env vars
├── docker-compose.yml          # Local dev setup
├── requirements.txt            # Python deps
└── README.md                   # Main readme
```

---

## 🎯 PREMIERS PAS (Checklist)

### Jour 1: Setup
- [ ] Clone repository
- [ ] Setup virtual env
- [ ] Install dependencies
- [ ] Configure .env
- [ ] Start Docker services
- [ ] Run test_connections.py (tous ✅)

### Jour 2: Familiarisation
- [ ] Lire MASTER_PLAN.md (comprendre architecture)
- [ ] Explorer structure code (src/)
- [ ] Lancer bot en mode simulation
- [ ] Observer logs

### Jour 3: Premiers Tests
- [ ] Obtenir testnet tokens (faucets)
- [ ] Configurer wallet testnet dans .env
- [ ] Lancer bot en mode testnet
- [ ] Exécuter 1 trade test

### Jour 4-5: Développement
- [ ] Choisir première feature à développer
- [ ] Créer branch Git
- [ ] Coder + tests
- [ ] Commit + Push

---

## 🆘 TROUBLESHOOTING

### Problème: Docker services ne démarrent pas

```bash
# Check ports disponibles
netstat -an | findstr "5432"  # PostgreSQL
netstat -an | findstr "6379"  # Redis
netstat -an | findstr "5672"  # RabbitMQ

# Si ports occupés, changer dans docker-compose.yml
# Ou arrêter services conflictuels

# Rebuild containers
docker-compose down -v
docker-compose up -d --build
```

---

### Problème: "Invalid RPC URL"

```bash
# Test RPC manually
curl https://eth-mainnet.alchemyapi.io/v2/YOUR_KEY \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# Should return: {"jsonrpc":"2.0","id":1,"result":"0x..."}

# Si erreur: vérifier API key Alchemy
```

---

### Problème: "Database connection failed"

```bash
# Check PostgreSQL running
docker-compose ps postgres

# If not running:
docker-compose up -d postgres

# Check logs
docker-compose logs postgres

# Test connection manually
docker exec -it cryptobot_postgres psql -U cryptobot -d cryptobot

# Inside psql:
\dt  # List tables
\q   # Quit
```

---

### Problème: "ModuleNotFoundError"

```bash
# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall

# Or use fresh venv
deactivate
rm -rf venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 📖 COMMANDES UTILES

### Docker
```bash
# Start all services
docker-compose up -d

# Stop all
docker-compose down

# View logs (all)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f postgres

# Restart service
docker-compose restart redis

# Remove everything (⚠️ deletes data)
docker-compose down -v
```

### Database
```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1

# View migration history
alembic history
```

### Git
```bash
# Create feature branch
git checkout -b feature/my-feature

# Commit
git add .
git commit -m "feat: add feature X"

# Push
git push origin feature/my-feature

# Pull latest
git pull origin main
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_orchestrator.py

# Run with coverage
pytest --cov=src tests/

# Run only fast tests (skip slow)
pytest -m "not slow"
```

---

## 🎓 RESSOURCES APPRENTISSAGE

### Si Débutant en Crypto Trading
1. **Binance Academy:** https://academy.binance.com
2. **CoinGecko Learn:** https://www.coingecko.com/learn
3. **YouTube:** "Crypto Trading for Beginners"

### Si Débutant en DeFi
1. **Uniswap Docs:** https://docs.uniswap.org
2. **Finematics (YouTube):** DeFi expliqué simplement
3. **Whiteboard Crypto:** Visual explanations

### Si Débutant en ML Trading
1. **Freqtrade Docs:** https://www.freqtrade.io
2. **QuantConnect:** https://www.quantconnect.com/learning
3. **Cours:** "Machine Learning for Trading" (Udacity)

---

## 💡 TIPS & BEST PRACTICES

### Sécurité
1. ⚠️ **NEVER** commit private keys
2. ⚠️ Use testnet pour tous premiers tests
3. ⚠️ Start with small capital ($100-500)
4. ⚠️ Setup alerts (Telegram) pour monitoring
5. ⚠️ Backup seeds/keys dans coffre physique

### Développement
1. ✅ Commit souvent (atomic commits)
2. ✅ Write tests AVANT de coder (TDD)
3. ✅ Document code (docstrings)
4. ✅ Code review (même si seul, relire lendemain)
5. ✅ Logs everywhere (debug facilité)

### Trading
1. 📊 Backtest TOUJOURS avant production
2. 📊 Paper trade au moins 1 semaine
3. 📊 Start small, scale progressivement
4. 📊 Never all-in sur un trade
5. 📊 Accept losses (inévitables)

---

## 🚀 NEXT STEPS

**Une fois setup terminé:**

1. **Read Master Plan** (2h)
   - Comprendre architecture globale
   - Vision à long terme

2. **Choose First Module** (30min)
   - Recommandé: Sniper Bot (plus simple que ML)
   - Ou News Trader (si préfères)

3. **Develop MVP** (1 semaine)
   - Feature minimale fonctionnelle
   - Tests sur testnet
   - Iterate

4. **Test Real Money** (petits montants)
   - $100-500 initial
   - Monitor closely
   - Learn from mistakes

5. **Scale Progressively**
   - Si profitable, augmenter capital graduellement
   - Ajouter modules progressivement
   - Améliorer constamment

---

## ✅ VALIDATION FINALE

**Avant de considérer setup complet:**

- [ ] Tous services Docker UP
- [ ] test_connections.py retourne tous ✅
- [ ] Bot démarre sans erreur
- [ ] Mode simulation fonctionne
- [ ] Logs s'affichent correctement
- [ ] Swagger API accessible
- [ ] Database schema créé (tables visibles)
- [ ] Redis cache fonctionne
- [ ] Premier trade testnet exécuté avec succès

**Si tous checked:** 🎉 **READY TO BUILD!**

---

## 📞 AIDE

**Si bloqué:**

1. **Check Logs:**
   ```bash
   docker-compose logs -f
   tail -f logs/cryptobot.log
   ```

2. **Search Docs:**
   - MASTER_PLAN.md
   - TECH_STACK_DETAILED.md

3. **Debug Mode:**
   ```bash
   LOG_LEVEL=DEBUG python src/main.py
   ```

4. **Ask Community:**
   - GitHub Issues
   - Discord/Telegram (si existe)

---

## 🎯 OBJECTIF PREMIÈRE SEMAINE

**Goal:** Bot capable d'exécuter 1 trade profitable sur testnet

**Success Criteria:**
- ✅ Infrastructure fonctionne
- ✅ Bot détecte opportunité (simulation ou real)
- ✅ Execute trade (testnet)
- ✅ Trade profitable (même $1)
- ✅ Aucun crash durant 24h

**Si atteint:** Prêt pour Phase 2 🚀

---

**Dernière mise à jour:** 22 Nov 2025  
**Version:** 1.0  
**Author:** Assistant IA

---

> 💡 **Remember:** "Every expert was once a beginner. Start small, learn fast, iterate constantly."

**Let's build the best crypto bot possible! 🤖💰**

