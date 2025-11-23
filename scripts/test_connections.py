"""
Test all critical connections
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.storage.database import Database
from src.execution.wallet_manager import WalletManager
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def test_all():
    """Test all connections"""
    print("\n[TEST] Testing Cryptobot Connections...\n")
    
    # Test Database
    print("[1] Testing PostgreSQL...")
    try:
        db = Database()
        await db.connect()
        is_healthy = await db.is_healthy()
        if is_healthy:
            print("   [OK] PostgreSQL: Connected!")
        else:
            print("   [ERROR] PostgreSQL: Unhealthy")
        await db.disconnect()
    except Exception as e:
        print(f"   [ERROR] PostgreSQL: Failed - {e}")
    
    # Test Wallet
    print("\n[2] Testing Wallet Manager...")
    try:
        wallet = WalletManager()
        await wallet.initialize()
        balances = await wallet.get_all_balances()
        print(f"   [OK] Wallet: Connected!")
        print(f"   Balance: ETH={balances.get('ETH', 0)}, BNB={balances.get('BNB', 0)}")
    except Exception as e:
        print(f"   [ERROR] Wallet: Failed - {e}")
    
    print("\n[OK] All tests completed!\n")


if __name__ == "__main__":
    asyncio.run(test_all())

