# Configuration Environment Variables

Copy these to your `.env` file and fill in your values.

```env
# ==========================================
# MODE (Start with simulation!)
# ==========================================
SIMULATION_MODE=True
USE_TESTNET=True
ENVIRONMENT=development

# ==========================================
# DATABASE
# ==========================================
DATABASE_URL=sqlite+aiosqlite:///./cryptobot.db

# ==========================================
# BINANCE API
# ==========================================
BINANCE_API_KEY=your_key
BINANCE_SECRET=your_secret

# ==========================================
# ETHEREUM RPC
# ==========================================
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
ETHEREUM_TESTNET_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY

# ==========================================
# WALLET (Use a dedicated trading wallet!)
# ==========================================
WALLET_PRIVATE_KEY=64_char_hex_key

# ==========================================
# RISK MANAGEMENT
# ==========================================
MAX_POSITION_SIZE_PCT=10.0
MAX_DAILY_LOSS_PCT=5.0
STOP_LOSS_PCT=15.0
TAKE_PROFIT_PCT=30.0
```

## For Real Trading

Set these values:
```env
SIMULATION_MODE=False
USE_TESTNET=False
ENVIRONMENT=production
```

⚠️ **NEVER commit your `.env` file to git!**
