# 🚀 SETUP SUPABASE & OPENAI - GUIDE COMPLET

## 📋 Ce que tu vas obtenir

Après ce setup, ton bot aura :
- ✅ **Analytics temps réel** stockées dans Supabase
- ✅ **AI Optimizer** qui analyse et améliore le bot automatiquement
- ✅ **Alertes intelligentes** (Telegram, Webhooks)
- ✅ **Dashboard avancé** avec métriques détaillées
- ✅ **Auto-optimisation** des paramètres

---

## 1️⃣ CRÉER COMPTE SUPABASE (5 min)

### Étape 1: Inscription
1. Va sur https://supabase.com
2. Clique "Start your project"
3. Connecte-toi avec GitHub (gratuit)

### Étape 2: Créer un projet
1. Clique "New project"
2. Nom: `cryptobot-analytics`
3. Database Password: **GÉNÈRE ET SAUVEGARDE**
4. Region: `Asia Southeast (Singapore)` ou la plus proche
5. Clique "Create new project"
6. **Attends 2 minutes** que le projet se crée

### Étape 3: Récupérer les clés
1. Dans ton projet, va dans "Settings" (⚙️) → "API"
2. **Copie ces 2 clés** (tu en auras besoin) :
   - `Project URL` → Exemple: `https://xxxxx.supabase.co`
   - `anon/public key` → Exemple: `eyJhbGciOiJIUz...`

### Étape 4: Créer les tables
1. Va dans "SQL Editor" (📝)
2. Clique "New query"
3. **Copie TOUT le contenu** du fichier `supabase_setup.sql`
4. Colle dans l'éditeur
5. Clique "Run" (▶️)
6. Tu devrais voir "Success. No rows returned"

✅ **SUPABASE EST PRÊT !**

---

## 2️⃣ CONFIGURER OPENAI (2 min)

### Étape 1: Créer compte OpenAI
1. Va sur https://platform.openai.com/signup
2. Inscris-toi (gratuit pour commencer)
3. Confirme ton email

### Étape 2: Obtenir clé API
1. Va sur https://platform.openai.com/api-keys
2. Clique "Create new secret key"
3. Nom: `cryptobot-optimizer`
4. **COPIE LA CLÉ** (tu ne la verras plus après !)
   - Format: `sk-proj-...` ou `sk-...`

### Étape 3: Ajouter du crédit
1. Va dans "Billing" → "Add payment method"
2. Ajoute $5-10 pour commencer
3. Le bot consommera ~$0.50-1/jour

✅ **OPENAI EST PRÊT !**

---

## 3️⃣ CONFIGURER LE BOT (3 min)

### Étape 1: Mettre à jour .env
Ouvre le fichier `.env` et ajoute :

```bash
# ==========================================
# SUPABASE (Analytics & Storage)
# ==========================================
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUz...

# ==========================================
# OPENAI (AI Optimizer)
# ==========================================
OPENAI_API_KEY=sk-proj-...

# ==========================================
# SMART ALERTS (Optionnel)
# ==========================================
TELEGRAM_BOT_TOKEN=  # Ton token Telegram si tu en as un
TELEGRAM_CHAT_ID=    # Ton chat ID
WEBHOOK_URL=         # URL webhook Discord/Slack (optionnel)

# ==========================================
# AI OPTIMIZER CONFIG
# ==========================================
ENABLE_AI_OPTIMIZER=True           # Activer l'AI optimizer
AI_AUTO_APPLY_SUGGESTIONS=False    # False = suggestions seulement, True = applique auto
```

### Étape 2: Installer dépendances
```bash
pip install -r requirements.txt
```

### Étape 3: Tester la connexion
```bash
python -c "from src.integrations.supabase_logger import SupabaseLogger; print('✅ Supabase OK')"
python -c "from src.integrations.ai_optimizer import AIOptimizer; print('✅ OpenAI OK')"
```

✅ **BOT EST CONFIGURÉ !**

---

## 4️⃣ TELEGRAM (Optionnel mais recommandé)

### Pourquoi ?
Reçois des alertes instantanées sur ton téléphone !

### Setup rapide
1. Ouvre Telegram
2. Cherche `@BotFather`
3. Envoie `/newbot`
4. Nom: `Cryptobot Alerts`
5. Username: `mon_cryptobot_bot` (doit finir par `_bot`)
6. **Copie le token** (format: `123456:ABCdefGHI...`)

7. Cherche `@userinfobot`
8. Envoie n'importe quoi
9. **Copie ton Chat ID** (nombre, ex: `987654321`)

10. Mets dans `.env` :
```bash
TELEGRAM_BOT_TOKEN=123456:ABCdefGHI...
TELEGRAM_CHAT_ID=987654321
```

✅ **TELEGRAM CONFIGURÉ !**

---

## 5️⃣ LANCER LE BOT

```bash
python src/main.py
```

Tu devrais voir :
```
✅ Supabase connected
🤖 AI Optimizer initialized (auto_apply=False)
🔧 Parameter Optimizer initialized
🚨 Smart Alerts System initialized
🚀 Supabase logger started
🚀 AI Optimizer started
✅ Bot Started
```

---

## 6️⃣ VÉRIFIER QUE ÇA MARCHE

### Dans Supabase
1. Va dans "Table Editor"
2. Ouvre la table `events`
3. Tu devrais voir l'événement "Bot Started"

### Dashboard
1. Ouvre https://cryptobot-ultimate-production.up.railway.app/
2. Tu devrais voir les métriques en temps réel

### Telegram (si configuré)
Tu devrais recevoir "✅ Bot Started"

---

## 7️⃣ UTILISER L'AI OPTIMIZER

### Mode 1: Suggestions seulement (Recommandé)
```bash
# Dans .env
AI_AUTO_APPLY_SUGGESTIONS=False
```

Le bot va :
- Analyser les performances toutes les 6h
- Te donner des suggestions d'amélioration
- **NE PAS appliquer automatiquement**

Tu verras dans les logs :
```
🔍 Starting AI analysis...
🤖 GPT-4 analysis: ...
✅ AI analysis completed: 3 suggestions
🔧 Would apply: MIN_ADVANCED_SCORE = 85 (reason: Win rate below target)
```

### Mode 2: Application automatique (Avancé)
```bash
# Dans .env
AI_AUTO_APPLY_SUGGESTIONS=True
```

⚠️ **ATTENTION**: Le bot va modifier ses propres paramètres automatiquement !

---

## 📊 DASHBOARD SUPABASE

### Requêtes utiles

**Win rate derniers 7 jours**:
```sql
SELECT get_win_rate(7);
```

**Top 10 symboles**:
```sql
SELECT * FROM get_top_symbols(10);
```

**Performance par heure**:
```sql
SELECT * FROM v_performance_by_hour;
```

**Alertes critiques**:
```sql
SELECT * FROM v_recent_critical_events;
```

---

## 🔧 TROUBLESHOOTING

### Erreur "Supabase not connected"
- Vérifie `SUPABASE_URL` et `SUPABASE_KEY` dans `.env`
- Va sur Supabase → Settings → API pour vérifier

### Erreur "OpenAI API key invalid"
- Vérifie `OPENAI_API_KEY` dans `.env`
- Va sur https://platform.openai.com/api-keys

### Pas d'alertes Telegram
- Vérifie `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`
- Teste avec `@userinfobot` pour avoir le bon Chat ID

### Tables Supabase vides
- Le bot doit tourner pour générer des données
- Attends quelques heures pour voir les premières métriques

---

## 🎯 PROCHAINES ÉTAPES

1. **Laisse tourner 24h** pour collecter des données
2. **Vérifie Supabase** pour voir les analytics
3. **Attends première analyse AI** (6h après démarrage)
4. **Décide si tu veux activer auto-apply** après 7 jours

---

## 📝 NOTES IMPORTANTES

- **Coût Supabase**: Gratuit jusqu'à 500MB (largement suffisant)
- **Coût OpenAI**: ~$0.50-1/jour avec GPT-4
- **Telegram**: Totalement gratuit
- **Railway**: $5/mois pour hébergement

**TOTAL estimé**: $10-15/mois

---

## ❓ QUESTIONS FRÉQUENTES

**Q: Est-ce que je DOIS utiliser Supabase ?**
R: Non, le bot peut tourner sans. Mais tu perds :
- Analytics avancées
- AI Optimizer
- Dashboard temps réel

**Q: AI_AUTO_APPLY_SUGGESTIONS=True est-il dangereux ?**
R: Oui, un peu. Laisse sur `False` au début pour voir les suggestions.
Active `True` après 2-3 semaines quand tu as confiance.

**Q: Combien de fois l'AI analyse-t-il ?**
R: Toutes les 6 heures par défaut (configurable)

**Q: Puis-je utiliser GPT-3.5 au lieu de GPT-4 ?**
R: Oui, modifie `model="gpt-4o"` → `model="gpt-3.5-turbo"` dans `ai_optimizer.py`
(Moins cher mais moins précis)

---

## 🆘 SUPPORT

Si tu as des problèmes :
1. Vérifie les logs du bot
2. Vérifie Supabase logs
3. Vérifie Railway logs
4. Crée une issue sur GitHub

**BON TRADING ! 🚀💰**
