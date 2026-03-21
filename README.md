# Cryptobot Ultimate

Bot de trading crypto multi-strategie avec ML et analyse AI.

## Status

| Parametre | Valeur |
|-----------|--------|
| Mode | SIMULATION (auto-unlock vers REAL apres validation) |
| Plateforme | Railway |
| Capital | $10,000 (virtuel) |
| Dashboard | Port 8080 (auth Bearer token) |

## Strategies actives

- **Grid Trading** (80% capital) - ETH/USDC (Base) + BNB/USDT (BSC), regime-adaptatif
- **Token Sniper** (20% capital) - Detection pools BSC/Base via DexScreener + GeckoTerminal

## Pipeline d'analyse

```
Signal detecte
  -> Honeypot Detector (GoPlus API)
  -> Rugpull Detector (holders, liquidite)
  -> Sentiment Analyzer (multi-source)
  -> Smart Entry (ML timing)
  -> Position Sizer (Kelly criterion)
  -> OpenAI LLM (GPT-4o-mini)
  -> Trade execute (simulation ou DEX reel)
```

## Architecture

```
src/
├── main.py                    # Point d'entree
├── healthcheck.py             # Dashboard HTTP Railway
├── core/
│   ├── orchestrator.py        # Chef d'orchestre principal
│   ├── safety_manager.py      # Sim/real, emergency stop
│   ├── config.py              # Config Pydantic (.env)
│   └── risk_manager.py        # Limites de risque
├── trading/
│   ├── dex_trader.py          # Execution DEX multi-chain
│   ├── grid_trader.py         # Grid trading adaptatif
│   ├── paper_trader.py        # Trading simule
│   └── ...                    # Backtest, ML model, data collector
├── modules/
│   ├── ai/                    # OpenAI, sentiment, position sizing
│   ├── geckoterminal/         # Pool detection, DexScreener, Gecko
│   ├── security/              # Honeypot, rugpull detection
│   └── momentum_detector.py   # Signaux swing/momentum TA
├── ml/auto_learner.py         # ML auto-apprentissage
├── data/storage/trade_recorder.py  # Persistence Supabase REST
├── notifications/telegram_bot.py
└── utils/                     # Indicateurs TA, helpers, logger
```

## Deploiement

```bash
railway link    # Premiere fois
railway up      # Deployer
railway logs    # Voir les logs
```

## Integrations

- **Supabase** : PostgreSQL (trades, events, stats) via REST API
- **OpenAI** : GPT-4o-mini pour analyse tokens + portfolio review
- **Telegram** : Notifications temps reel
- **Binance** : WebSocket prix + donnees historiques
- **DexScreener / GeckoTerminal** : Detection pools
- **GoPlus** : Securite tokens (honeypot, rugpull)
- **Web3** : Execution DEX (BSC, Base, ETH, Arbitrum)

## Avertissement

Ce bot demarre en mode SIMULATION. Le passage en mode reel est controle par le Safety Manager apres validation (20+ trades, WR > 35%, PnL > $0).
