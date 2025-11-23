# 💻 STACK TECHNIQUE DÉTAILLÉ - CRYPTOBOT ULTIMATE

**Date:** 22 Novembre 2025  
**Purpose:** Spécifications techniques complètes et justifications

---

## 🎯 CRITÈRES DE SÉLECTION

Chaque technologie a été choisie selon:
1. **Performance** (latence, throughput)
2. **Fiabilité** (production-proven)
3. **Écosystème** (libraries, community)
4. **Coût** (total cost of ownership)
5. **Scalabilité** (croissance future)

---

## 🐍 BACKEND CORE

### Python 3.11+
**Rôle:** Language principal pour orchestrateur et modules non-critiques

**Pourquoi Python:**
- ✅ Écosystème ML/AI le plus riche (PyTorch, TensorFlow, scikit-learn)
- ✅ Rapidité de développement (prototyping)
- ✅ Libraries blockchain excellentes (web3.py, solana-py)
- ✅ Async natif (asyncio) pour opérations I/O
- ✅ Large communauté crypto/trading

**Librairies clés:**
```python
# Core
asyncio, aiohttp, uvloop  # Async performance
fastapi, pydantic         # API framework
click                     # CLI tools

# Data
pandas, polars            # DataFrames
numpy, scipy              # Numerical computing
pyarrow                   # Columnar data

# Blockchain
web3.py                   # Ethereum/EVM
solana-py                 # Solana
ccxt                      # CEX trading
eth-abi, eth-account      # Low-level Ethereum

# ML/AI
torch, tensorflow         # Deep learning
transformers              # NLP (Hugging Face)
stable-baselines3         # Reinforcement Learning
scikit-learn              # Classical ML
xgboost, lightgbm         # Gradient boosting

# Database
psycopg2, asyncpg         # PostgreSQL
redis-py                  # Redis
sqlalchemy                # ORM

# Monitoring
prometheus-client         # Metrics
sentry-sdk                # Error tracking

# Testing
pytest, pytest-asyncio    # Testing framework
hypothesis                # Property-based testing
```

**Performance Tips:**
- Utiliser `uvloop` pour remplacer event loop standard (+30-40% vitesse)
- Compiler code critique avec Cython ou Numba
- Profiling avec `cProfile` et `py-spy`

---

### Rust
**Rôle:** Modules haute performance (sniper, arbitrage HFT)

**Pourquoi Rust:**
- ✅ Performance native (équivalent C++)
- ✅ Memory safety (pas de bugs mémoire)
- ✅ Concurrence sans data races
- ✅ Excellent pour blockchain (Solana écrit en Rust)
- ✅ Bindings Python faciles (PyO3)

**Crates recommandées:**
```rust
// Async runtime
tokio                     // Async runtime
async-std                 // Alternative à tokio

// Blockchain
ethers-rs                 // Ethereum
solana-client, solana-sdk // Solana
anchor-lang                // Solana smart contracts

// Serialization
serde, serde_json         // JSON
bincode                   // Binary

// HTTP
reqwest                   // HTTP client
axum                      // Web framework

// Utils
rayon                     // Data parallelism
crossbeam                 // Concurrency primitives
```

**Quand utiliser Rust:**
- Sniper bot (mempool scanning < 10ms)
- Arbitrage HFT (latence < 50ms critique)
- Smart contract analysis (parsing rapide)
- Order routing (performance max)

**Architecture:**
```
Python (orchestrateur)
   ↓ (via PyO3)
Rust (module high-perf)
   ↓
Blockchain/Exchange
```

---

## 🗄️ DATABASES & STORAGE

### PostgreSQL 15+
**Rôle:** Database principale (données structurées)

**Schema types:**
- **Trades table:** Historique des trades
- **Positions table:** Positions ouvertes
- **Wallets table:** Multi-chain wallets
- **Strategies table:** Config par stratégie
- **Performance table:** Métriques journalières

**Extensions:**
```sql
-- Time-series data
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- JSON operations
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Full-text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

**Optimisations:**
- Partitioning par date (trades)
- Indexes composites sur (strategy, timestamp)
- Connection pooling (PgBouncer)

---

### TimescaleDB
**Rôle:** Time-series data (OHLCV, metrics)

**Pourquoi TimescaleDB:**
- ✅ Extension PostgreSQL (pas de nouvelle DB)
- ✅ Compression automatique (70-90% gain espace)
- ✅ Queries time-series optimisées
- ✅ Continuous aggregates (matérialisées auto)

**Hypertables:**
```sql
-- OHLCV data
CREATE TABLE ohlcv (
  time TIMESTAMPTZ NOT NULL,
  symbol TEXT NOT NULL,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC
);
SELECT create_hypertable('ohlcv', 'time');

-- Compress data > 7 days
ALTER TABLE ohlcv SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'symbol'
);
SELECT add_compression_policy('ohlcv', INTERVAL '7 days');
```

---

### Redis 7+
**Rôle:** Cache, queues, pub/sub, real-time data

**Use cases:**
1. **Cache:** Prix actuel, wallet balances
2. **Queue:** Job queue pour tasks async
3. **Pub/Sub:** Communication inter-modules
4. **Rate limiting:** API calls tracking
5. **Session:** WebSocket connections

**Data structures:**
```redis
# Prix actuel (TTL 10 sec)
SET price:BTC:USDT "43250.50" EX 10

# Orderbook snapshot (Sorted Set)
ZADD orderbook:ETH:asks 1850.25 "10.5"

# Pending transactions (List)
LPUSH pending_tx "0xabc..."

# Module health (Hash)
HSET module:sniper status "running" last_trade "1700000000"

# Pub/Sub
PUBLISH channel:alerts '{"type":"whale_move","amount":1000}'
```

**Performance:**
- Persistence: RDB + AOF (safety vs performance)
- Clustering: Redis Cluster si > 100k ops/sec
- Sentinel: High availability

---

### MongoDB (Optionnel)
**Rôle:** Logs, documents non-structurés

**Pourquoi:**
- ✅ Flexible schema (logs)
- ✅ Excellent pour analytics
- ✅ Aggregation pipeline puissante

**Collections:**
- `trade_logs`: Tous détails de trades
- `error_logs`: Stack traces
- `sentiment_data`: Tweets/posts raw

---

## ⚡ MESSAGE QUEUES

### RabbitMQ vs Kafka

**RabbitMQ** (Recommandé pour démarrer)
**Pros:**
- ✅ Setup simple
- ✅ Faible latence (< 1ms)
- ✅ Routing flexible (exchanges, bindings)
- ✅ Excellent pour tasks async

**Use case:**
```python
# Module Sniper envoie nouveau trade
channel.basic_publish(
    exchange='trades',
    routing_key='sniper.new_token',
    body=json.dumps(trade_data)
)

# Orchestrateur reçoit
def callback(ch, method, properties, body):
    trade = json.loads(body)
    update_portfolio(trade)
```

**Apache Kafka** (Si scaling massif)
**Pros:**
- ✅ Throughput énorme (millions msgs/sec)
- ✅ Replay capability
- ✅ Log-based architecture

**Quand Kafka:**
- Si > 10k trades/jour
- Si besoin historique rejoué
- Si multi-datacenter

---

## 🔗 BLOCKCHAIN INTERACTIONS

### Ethereum/EVM Chains

#### web3.py
**Pourquoi:**
- ✅ Pythonic, facile
- ✅ Bien maintenu (Ethereum Foundation)
- ✅ Supporte tous providers (HTTP, WS, IPC)

**Example:**
```python
from web3 import Web3

# Connect
w3 = Web3(Web3.HTTPProvider('https://eth-mainnet.alchemyapi.io/v2/KEY'))

# Read contract
contract = w3.eth.contract(address=uniswap_v2_router, abi=ABI)
amounts_out = contract.functions.getAmountsOut(
    amountIn=w3.toWei(1, 'ether'),
    path=[WETH, USDC]
).call()

# Send transaction (async)
tx = contract.functions.swapExactETHForTokens(
    amountOutMin=min_tokens,
    path=[WETH, TOKEN],
    to=wallet_address,
    deadline=deadline
).buildTransaction({
    'from': wallet_address,
    'gas': 200000,
    'gasPrice': w3.eth.gas_price * 2,  # Priority
    'nonce': w3.eth.get_transaction_count(wallet_address)
})
signed = w3.eth.account.sign_transaction(tx, private_key)
tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
```

#### Flashbots
**Pourquoi:**
- ✅ MEV protection (transactions privées)
- ✅ Gas savings (pas de failed tx coûteuses)
- ✅ Priorité garantie si bundle accepté

**Integration:**
```python
from flashbots import flashbot
from web3 import Web3

w3 = Web3(Web3.HTTPProvider('https://...'))
flashbot(w3, signature_account)

# Bundle multiple transactions
bundle = [
    {
        "transaction": {
            "to": token_address,
            "value": 0,
            "data": buy_data,
            ...
        },
        "signer": account
    },
    {
        "transaction": {
            "to": token_address,
            "value": 0,
            "data": sell_data,
            ...
        },
        "signer": account
    }
]

# Simulate then send
result = w3.flashbots.simulate(bundle, block_number)
if result['results'][0]['error'] is None:
    w3.flashbots.send_bundle(bundle, target_block_number=block_number + 1)
```

#### Node Providers
**Options:**
1. **Alchemy** (Recommandé)
   - Free tier: 300M compute units/mois
   - Enhanced APIs (notify, trace)
   - 99.9% uptime SLA
   
2. **Infura**
   - Stable, réputé
   - Archive nodes
   
3. **QuickNode**
   - Ultra-low latency
   - Customizable

4. **Self-hosted** (Geth/Erigon)
   - Latence minimale
   - Coût: hardware + maintenance

---

### Solana

#### solana-py
```python
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solders.keypair import Keypair

async def swap_on_raydium():
    client = AsyncClient("https://api.mainnet-beta.solana.com")
    
    # Build transaction
    tx = Transaction()
    tx.add(swap_instruction)
    
    # Send with priority fee
    result = await client.send_transaction(
        tx, 
        keypair,
        opts=TxOpts(
            skip_preflight=True,
            preflight_commitment="confirmed"
        )
    )
    return result
```

#### Jito (MEV on Solana)
**Pourquoi:**
- ✅ Transactions landing garanties
- ✅ Bundles atomiques
- ✅ MEV tips instead of priority fees

**Setup:**
```bash
# Use Jito RPC
https://mainnet.block-engine.jito.wtf
```

---

### Multi-Exchange (CEX)

#### CCXT
**Pourquoi:**
- ✅ 100+ exchanges supportés
- ✅ API unifié
- ✅ Excellent pour arbitrage

```python
import ccxt.async_support as ccxt

# Init exchanges
binance = ccxt.binance({'apiKey': '...', 'secret': '...'})
coinbase = ccxt.coinbasepro({'apiKey': '...', 'secret': '...'})

# Fetch orderbooks
async def check_arbitrage():
    ticker_binance = await binance.fetch_ticker('BTC/USDT')
    ticker_coinbase = await coinbase.fetch_ticker('BTC/USD')
    
    spread = ticker_coinbase['bid'] - ticker_binance['ask']
    if spread > threshold:
        await execute_arbitrage(...)
```

---

## 🧠 AI/ML STACK

### PyTorch 2.0+
**Rôle:** Framework ML principal

**Pourquoi PyTorch:**
- ✅ Pythonic, intuitif
- ✅ Dynamic computation graph (flexibilité)
- ✅ Excellent pour recherche + production
- ✅ TorchScript (compilation pour prod)
- ✅ Meilleur ecosystem NLP (Hugging Face)

**Models pour trading:**

#### 1. LSTM pour Time-Series
```python
import torch
import torch.nn as nn

class PriceLSTM(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)  # Predict next price
    
    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out

# Training
model = PriceLSTM(input_size=50, hidden_size=128, num_layers=2)
criterion = nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
```

#### 2. Transformer pour Sentiment
```python
from transformers import BertForSequenceClassification, BertTokenizer

# Fine-tuned on crypto tweets
model = BertForSequenceClassification.from_pretrained('bert-base-uncased', num_labels=3)
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

def predict_sentiment(text):
    inputs = tokenizer(text, return_tensors='pt', padding=True, truncation=True)
    outputs = model(**inputs)
    prediction = torch.argmax(outputs.logits, dim=1)
    # 0: negative, 1: neutral, 2: positive
    return prediction.item()
```

#### 3. Reinforcement Learning (PPO)
```python
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
import gym

# Custom trading environment
class TradingEnv(gym.Env):
    def __init__(self, df):
        super().__init__()
        self.df = df
        self.action_space = gym.spaces.Discrete(3)  # Buy, Hold, Sell
        self.observation_space = gym.spaces.Box(
            low=0, high=1, shape=(50,), dtype=np.float32
        )
    
    def step(self, action):
        # Execute trade, calculate reward
        ...
        return observation, reward, done, info

# Train agent
env = DummyVecEnv([lambda: TradingEnv(df)])
model = PPO('MlpPolicy', env, verbose=1)
model.learn(total_timesteps=100000)
```

---

### MLflow
**Rôle:** Experiment tracking & model management

**Features:**
- 📊 Track metrics, parameters, artifacts
- 🔄 Model versioning
- 🚀 Model serving (REST API)
- 🔍 Experiment comparison

```python
import mlflow

mlflow.set_experiment("lstm_price_prediction")

with mlflow.start_run():
    # Log params
    mlflow.log_param("hidden_size", 128)
    mlflow.log_param("learning_rate", 0.001)
    
    # Train
    for epoch in range(100):
        train_loss = train_epoch()
        val_loss = validate()
        
        # Log metrics
        mlflow.log_metric("train_loss", train_loss, step=epoch)
        mlflow.log_metric("val_loss", val_loss, step=epoch)
    
    # Save model
    mlflow.pytorch.log_model(model, "model")
```

---

## ☁️ INFRASTRUCTURE

### Cloud Provider: AWS (Recommandé)

**Services utilisés:**

#### EC2 (Compute)
- **Instance type:** c6i.2xlarge (compute optimized)
  - 8 vCPU, 16GB RAM
  - Cost: ~$250/mois
- **OS:** Ubuntu 22.04 LTS
- **Régions:** us-east-1 (Virginie) + eu-west-1 (Irlande)
  - Latence minimale vers exchanges

#### RDS (PostgreSQL)
- **Instance:** db.r6g.xlarge (4 vCPU, 32GB RAM)
- **Storage:** GP3 SSD avec autoscaling
- **Backups:** Automated daily + point-in-time recovery

#### ElastiCache (Redis)
- **Instance:** cache.r6g.large (2 vCPU, 13GB RAM)
- **Cluster mode enabled** (sharding)

#### S3 (Storage)
- **Use cases:**
  - Backups database
  - Model artifacts
  - Historical data archives
  - Logs long-term

#### Lambda (Serverless)
- **Use cases:**
  - Webhooks handlers
  - Scheduled tasks (cron)
  - Alert notifications

#### CloudWatch (Monitoring)
- Logs aggregation
- Custom metrics
- Dashboards
- Alerts (SNS)

---

### Docker & Kubernetes

#### Docker
**Containers:**
1. `cryptobot-core`: Orchestrateur + APIs
2. `cryptobot-sniper`: Module sniper (Rust)
3. `cryptobot-ml`: ML inference server
4. `postgres`: Database
5. `redis`: Cache
6. `rabbitmq`: Message queue
7. `grafana`: Monitoring dashboard
8. `prometheus`: Metrics collector

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  core:
    build: ./src/core
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres/cryptobot
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    ports:
      - "8000:8000"
  
  sniper:
    build: ./src/modules/sniper
    environment:
      - RPC_URL=https://...
    
  postgres:
    image: timescale/timescaledb:latest-pg15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=secret
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
  
  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "15672:15672"  # Management UI
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./monitoring/grafana:/etc/grafana/provisioning

volumes:
  postgres_data:
  redis_data:
```

#### Kubernetes (Production)
**Pourquoi K8s:**
- ✅ Auto-scaling (HPA)
- ✅ Self-healing (restarts auto)
- ✅ Rolling updates (zero downtime)
- ✅ Secrets management
- ✅ Load balancing

**Cluster setup:**
- **Node pool:** 3 nodes (c6i.2xlarge)
- **Managed K8s:** EKS (AWS) ou GKE (GCP)

---

## 📊 MONITORING & OBSERVABILITY

### Prometheus + Grafana

**Metrics à tracker:**
```python
from prometheus_client import Counter, Histogram, Gauge

# Counters
trades_total = Counter('trades_total', 'Total trades', ['strategy', 'outcome'])
trades_total.labels(strategy='sniper', outcome='win').inc()

# Histograms (latency)
trade_latency = Histogram('trade_latency_seconds', 'Trade execution time')
with trade_latency.time():
    execute_trade()

# Gauges (real-time values)
portfolio_value = Gauge('portfolio_value_usd', 'Current portfolio value')
portfolio_value.set(125000.50)
```

**Grafana Dashboards:**
1. **Portfolio Overview**
   - Total value (line chart)
   - Daily PnL (bar chart)
   - Allocation pie chart
   
2. **Trading Activity**
   - Trades/hour (heatmap)
   - Win rate (gauge)
   - Avg profit per trade
   
3. **System Health**
   - CPU/Memory usage
   - API latency
   - Error rate
   
4. **Strategy Performance**
   - ROI par stratégie
   - Sharpe ratio
   - Max drawdown

---

### Sentry (Error Tracking)

```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://...",
    traces_sample_rate=1.0,
    environment="production"
)

# Automatic error capture
try:
    risky_operation()
except Exception as e:
    sentry_sdk.capture_exception(e)
```

**Benefits:**
- 📧 Instant email/Slack alerts
- 🔍 Full stack traces
- 📊 Error grouping & trends
- 🔗 Integration avec GitHub (issues auto)

---

## 🔐 SECURITY

### Key Management

**Never hardcode private keys!**

#### Option 1: Hardware Wallet (Ledger/Trezor)
**Pros:**
- ✅ Maximum security (keys offline)
- ✅ Require physical confirmation

**Cons:**
- ❌ Pas fully automated (require human)
- ❌ Latency (USB communication)

**Use case:** Cold storage, gros montants

#### Option 2: AWS Secrets Manager
```python
import boto3

client = boto3.client('secretsmanager')
response = client.get_secret_value(SecretId='cryptobot/private_key')
private_key = response['SecretString']
```

#### Option 3: HashiCorp Vault
**Pros:**
- ✅ Rotation automatique
- ✅ Audit logs
- ✅ Dynamic secrets

---

### Multi-Sig Wallets

**Setup:**
- 3-of-5 multi-sig (3 sigs required)
- Signers: Hardware wallet + 2 servers + backup

**Gnosis Safe:**
```python
# Use Safe SDK
from gnosis.safe import Safe

safe = Safe('0x...', ethereum_client)
tx = safe.build_multisig_tx(
    to='0x...',
    value=0,
    data=swap_data
)
safe.sign_transaction(tx, private_key)
```

---

## 🧪 TESTING

### Pyramid of Tests

```
      /\
     /  \    E2E (5%)
    /────\
   / Unit \  Integration (15%)
  /────────\
 /  Unit    \ Unit Tests (80%)
/────────────\
```

### Unit Tests (pytest)
```python
import pytest
from decimal import Decimal

def test_calculate_profit():
    entry = Decimal('100')
    exit = Decimal('150')
    fees = Decimal('2')
    
    profit = calculate_profit(entry, exit, fees)
    
    assert profit == Decimal('48')  # (150 - 100 - 2)

@pytest.mark.asyncio
async def test_fetch_price():
    price = await fetch_price('BTC', 'USDT')
    assert price > 0
    assert isinstance(price, Decimal)
```

### Integration Tests
```python
@pytest.mark.integration
async def test_full_trade_flow():
    # Setup testnet
    bot = TradingBot(network='goerli')
    
    # Execute trade
    result = await bot.execute_trade({
        'type': 'buy',
        'symbol': 'WETH',
        'amount': 0.1
    })
    
    assert result['status'] == 'success'
    assert result['tx_hash'].startswith('0x')
```

### Backtesting
```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    def __init__(self):
        self.sma = bt.indicators.SMA(self.data.close, period=20)
    
    def next(self):
        if self.data.close[0] > self.sma[0]:
            self.buy()
        elif self.data.close[0] < self.sma[0]:
            self.sell()

# Run backtest
cerebro = bt.Cerebro()
cerebro.addstrategy(MyStrategy)
cerebro.adddata(data_feed)
cerebro.run()
```

---

## 📚 DÉPENDANCES FINALES

### requirements.txt
```txt
# Core
python==3.11.5
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.4.2
python-dotenv==1.0.0

# Async
aiohttp==3.9.0
asyncio==3.4.3
uvloop==0.19.0

# Blockchain
web3==6.11.3
solana==0.30.2
ccxt==4.1.22
eth-account==0.10.0

# Database
asyncpg==0.29.0
psycopg2-binary==2.9.9
redis==5.0.1
sqlalchemy==2.0.23

# ML/AI
torch==2.1.1
transformers==4.35.2
scikit-learn==1.3.2
xgboost==2.0.2
stable-baselines3==2.2.1

# Data
pandas==2.1.3
polars==0.19.19
numpy==1.26.2

# Monitoring
prometheus-client==0.19.0
sentry-sdk==1.38.0

# Utils
python-telegram-bot==20.7
requests==2.31.0
websockets==12.0
```

---

## 🚀 PROCHAINES ÉTAPES

1. **Valider ce stack** avec l'équipe
2. **Setup environnement** dev local
3. **Créer repo Git** avec structure
4. **Implémenter** Core Orchestrator minimal
5. **Premiers tests** sur testnet

---

**Dernière mise à jour:** 22 Nov 2025  
**Version:** 1.0  
**Status:** Spécifications finales

