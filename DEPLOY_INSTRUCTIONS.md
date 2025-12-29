# 🚀 INSTRUCTIONS DE DÉPLOIEMENT

## ⚠️ PROBLÈME ACTUEL

GitHub bloque le push car il a détecté la clé API OpenAI dans `.env`.

## ✅ SOLUTION

### Option 1: Autoriser le push (RAPIDE)
1. Va sur ce lien: https://github.com/DaCaTisHere/CBT/security/secret-scanning/unblock-secret/37WxqWjPoEUTq93vdHXcRxS5nwK
2. Clique "Allow secret"
3. Retourne ici et fais:
```bash
git push origin main --force
```

### Option 2: Nettoyer l'historique (PROPRE mais plus long)
```bash
# Réinitialiser au commit précédent
git reset --soft HEAD~1

# Retirer .env du staging
git reset HEAD .env

# Recommit sans .env
git commit -m "v4.1: OpenAI + Scripts (sans secrets)"

# Push
git push origin main
```

## 🔑 CONFIGURER RAILWAY

Une fois le push réussi:

1. Va sur Railway → ton projet
2. Variables → Add variable
3. Ajoute (avec TA vraie clé OpenAI):
```
OPENAI_API_KEY=sk-proj-VOTRE_CLE_OPENAI_ICI
OPENAI_MODEL=gpt-4o
ENABLE_AI_OPTIMIZER=True
AI_AUTO_APPLY_SUGGESTIONS=False
```

4. Le bot va redéployer automatiquement

## ✅ VÉRIFICATION

```bash
railway logs
```

Tu dois voir:
```
[OK] OpenAI connecte!
AI Optimizer initialized
Bot started
```

## 🎯 ENSUITE

Le bot tourne avec AI Optimizer !

Pour Supabase (optionnel):
- Lis `QUICK_START.md`
- Ou `SETUP_SUPABASE.md`
