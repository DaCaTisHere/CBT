# DÉPLOIEMENT RAILWAY - 3 ÉTAPES SIMPLES

## ✅ Ce qui est déjà fait :
- ✅ Projet Railway créé : cryptobot-ultimate
- ✅ Service "cryptobot" créé
- ✅ PostgreSQL ajouté
- ✅ Code commité dans git local

## 🚀 ÉTAPE 1 : Créer repo GitHub

```powershell
# Va sur https://github.com/new
# Créer un nouveau repo : "cryptobot-ultimate"
# NE PAS initialiser avec README
```

## 🚀 ÉTAPE 2 : Push le code

```powershell
cd "C:\Users\plani\Documents\GANG\Nouveau dossier"
git remote add origin https://github.com/TON_USERNAME/cryptobot-ultimate.git
git push -u origin main
```

## 🚀 ÉTAPE 3 : Connecter à Railway

1. Va sur https://railway.app/project/e602eb82-97d7-42cf-8242-f406a1e9657d
2. Clique sur le service "cryptobot"
3. Settings → Connect Repo → Sélectionne ton repo GitHub
4. Railway déploiera automatiquement !

## ⚙️ ÉTAPE 4 : Ajouter les variables

Dans Railway dashboard → cryptobot → Variables, ajoute :

```
ETHEREUM_RPC_URL=https://eth-mainnet.alchemyapi.io/v2/-kfSEIZonzlB1URjxuXCfvTGotsUOuNJ
WALLET_PRIVATE_KEY=0x6a181616675cc70c9b60498bda056c2903f43b6bdf5d8ce2d2f037e8ca40a36c
BINANCE_API_KEY=t3FIITQ6wHHH693Jfp5KYktGAUrkMQrDC8RyWEPuU5cNdAgqwZnDSHKhh50f8QSK
BINANCE_SECRET=AhOE9MmaPsi47Z5jYTBO6Fy4qRQCFy18VFvs27ozmNR0kHZiuyK1LQyr5Hqofqvu
USE_TESTNET=true
ENABLE_SNIPER=true
ENABLE_NEWS_TRADER=true
MAX_POSITION_SIZE_PCT=10.0
MAX_DAILY_LOSS_PCT=5.0
STOP_LOSS_PCT=15.0
```

(Copier toutes les variables depuis .env)

## ✅ C'est tout !

Railway détectera Python, installera les dépendances et lancera le bot automatiquement !

