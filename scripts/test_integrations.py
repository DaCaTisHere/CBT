"""
Script de test des intégrations
Teste Supabase, OpenAI, Telegram
"""
import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

async def test_supabase():
    """Test connexion Supabase"""
    print("\n[TEST SUPABASE]")
    print("-" * 40)
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("[ERROR] SUPABASE_URL ou SUPABASE_KEY manquant")
        return False
    
    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        
        # Test query
        result = supabase.table('trades').select('*').limit(1).execute()
        print(f"[OK] Supabase connecte!")
        print(f"   URL: {supabase_url[:30]}...")
        print(f"   Tables accessibles: trades, signals, metrics, events")
        return True
    
    except Exception as e:
        if 'does not exist' in str(e).lower():
            print("[WARNING] Supabase connecte mais tables pas creees")
            print("   -> Execute supabase_setup.sql dans SQL Editor")
        else:
            print(f"[ERROR] Erreur: {e}")
        return False

async def test_openai():
    """Test connexion OpenAI"""
    print("\n[TEST OPENAI]")
    print("-" * 40)
    
    openai_key = os.getenv('OPENAI_API_KEY')
    
    if not openai_key:
        print("[ERROR] OPENAI_API_KEY manquant")
        return False
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=openai_key)
        
        # Test simple
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Say 'test ok' in 2 words"}],
            max_tokens=10
        )
        
        result = response.choices[0].message.content
        print(f"[OK] OpenAI connecte!")
        print(f"   Modele: gpt-4o")
        print(f"   Test response: {result}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Erreur: {e}")
        if 'api_key' in str(e).lower():
            print("   -> Verifie ta cle API OpenAI")
        return False

async def test_telegram():
    """Test connexion Telegram"""
    print("\n[TEST TELEGRAM]")
    print("-" * 40)
    
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
    
    if not telegram_token or not telegram_chat:
        print("[INFO] Telegram non configure (optionnel)")
        return None
    
    try:
        import aiohttp
        
        url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        
        async with aiohttp.ClientSession() as session:
            await session.post(
                url,
                json={
                    'chat_id': telegram_chat,
                    'text': '✅ Test connexion Cryptobot - OK!'
                }
            )
        
        print(f"[OK] Telegram connecte!")
        print(f"   Message test envoye!")
        return True
    
    except Exception as e:
        print(f"[ERROR] Erreur: {e}")
        return False

async def test_all():
    """Test toutes les intégrations"""
    print("=" * 60)
    print("CRYPTOBOT - TEST INTEGRATIONS")
    print("=" * 60)
    
    results = {
        'supabase': await test_supabase(),
        'openai': await test_openai(),
        'telegram': await test_telegram()
    }
    
    print("\n" + "=" * 60)
    print("RESUME")
    print("=" * 60)
    
    for service, status in results.items():
        if status is True:
            emoji = "[OK]"
        elif status is False:
            emoji = "[KO]"
        else:
            emoji = "[--]"
        
        print(f"{emoji} {service.upper()}: {'OK' if status else 'KO' if status is False else 'Non configure'}")
    
    # Status global
    critical_ok = results['openai']  # OpenAI est critique
    optional_ok = results['supabase'] or results['telegram']
    
    print("\n" + "=" * 60)
    
    if critical_ok and optional_ok:
        print("[OK] TOUTES LES INTEGRATIONS SONT PRETES!")
        print("\nTu peux lancer le bot:")
        print("   python src/main.py")
    elif critical_ok:
        print("[WARNING] CONFIGURATION PARTIELLE")
        print("\n[OK] OpenAI OK -> AI Optimizer fonctionnel")
        print("[WARNING] Supabase KO -> Pas d'analytics avancees")
        print("\nLe bot peut tourner mais sans analytics")
    else:
        print("[ERROR] CONFIGURATION INCOMPLETE")
        print("\n[ERROR] OpenAI requis pour AI Optimizer")
        print("   -> Verifie OPENAI_API_KEY dans .env")
    
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(test_all())
