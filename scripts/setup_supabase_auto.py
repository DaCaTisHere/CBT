"""
Script d'auto-configuration Supabase
Execute automatiquement le schema SQL
"""
import os
import sys
from pathlib import Path
from supabase import create_client, Client

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def setup_supabase():
    """Configure automatiquement Supabase"""
    
    # Lire les credentials depuis .env
    from dotenv import load_dotenv
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("❌ ERREUR: SUPABASE_URL et SUPABASE_KEY requis dans .env")
        print("\n📝 INSTRUCTIONS:")
        print("1. Va sur https://supabase.com")
        print("2. Crée un projet 'cryptobot-analytics'")
        print("3. Settings → API")
        print("4. Copie 'Project URL' et 'anon public key'")
        print("5. Ajoute dans .env:")
        print("   SUPABASE_URL=https://xxxxx.supabase.co")
        print("   SUPABASE_KEY=eyJhbGci...")
        return False
    
    print("🔗 Connexion à Supabase...")
    
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        print("✅ Connexion réussie!")
        
        # Lire le schema SQL
        sql_file = Path(__file__).parent.parent / 'supabase_setup.sql'
        
        if not sql_file.exists():
            print(f"❌ Fichier SQL introuvable: {sql_file}")
            return False
        
        print(f"📄 Lecture du schema SQL...")
        sql_content = sql_file.read_text(encoding='utf-8')
        
        # Séparer les commandes SQL
        # Note: Supabase REST API ne peut pas exécuter du SQL directement
        # Il faut utiliser le SQL Editor ou l'API Management
        
        print("\n⚠️ CONFIGURATION MANUELLE REQUISE")
        print("=" * 60)
        print("Le MCP Supabase ne permet pas d'exécuter du SQL DDL.")
        print("\n📝 ÉTAPES À SUIVRE:")
        print("1. Va sur ton projet Supabase")
        print("2. Ouvre 'SQL Editor'")
        print("3. Clique 'New query'")
        print("4. Copie TOUT le contenu de: supabase_setup.sql")
        print("5. Colle dans l'éditeur")
        print("6. Clique 'Run' (▶️)")
        print("7. Tu dois voir 'Success. No rows returned'")
        print("=" * 60)
        
        # Tester la connexion en listant les tables
        print("\n🔍 Test de connexion...")
        
        # Essayer de query une table (même si elle n'existe pas encore)
        try:
            result = supabase.table('trades').select('*').limit(1).execute()
            print("✅ Table 'trades' existe déjà!")
            print(f"   Nombre de trades: {len(result.data)}")
            return True
        except Exception as e:
            if 'relation' in str(e).lower() or 'does not exist' in str(e).lower():
                print("⚠️ Tables pas encore créées")
                print("   → Suis les étapes ci-dessus pour créer les tables")
                return False
            else:
                print(f"❌ Erreur: {e}")
                return False
    
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return False

if __name__ == '__main__':
    print("🤖 CRYPTOBOT - AUTO-SETUP SUPABASE")
    print("=" * 60)
    
    success = setup_supabase()
    
    if success:
        print("\n✅ SUPABASE CONFIGURÉ!")
        print("\n🚀 Prochaines étapes:")
        print("1. Le bot peut maintenant logger dans Supabase")
        print("2. L'AI Optimizer est activé")
        print("3. Lance le bot: python src/main.py")
    else:
        print("\n⚠️ CONFIGURATION INCOMPLÈTE")
        print("Suis les instructions ci-dessus")
    
    print("\n" + "=" * 60)
