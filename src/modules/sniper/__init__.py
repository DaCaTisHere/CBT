"""
Sniper Bot Module

Exports all sniper bot components for easy importing.
Note: Requires web3 package. If not installed, dummy classes are provided.
"""

# Check if web3 is available
WEB3_AVAILABLE = False
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    pass

if WEB3_AVAILABLE:
    from src.modules.sniper.sniper_bot import SniperBot
    from src.modules.sniper.contract_analyzer import ContractAnalyzer
    from src.modules.sniper.mempool_monitor import MempoolMonitor, MempoolMonitorV3
    from src.modules.sniper.flashbots_executor import FlashbotsExecutor, DirectExecutor
    from src.modules.sniper.strategy import SniperStrategy
else:
    # Dummy classes when web3 is not available
    class SniperBot:
        """Dummy SniperBot - web3 not installed"""
        def __init__(self, *args, **kwargs):
            pass
        async def start(self):
            pass
        async def stop(self):
            pass
    
    class ContractAnalyzer:
        """Dummy ContractAnalyzer - web3 not installed"""
        def __init__(self, *args, **kwargs):
            pass
    
    class MempoolMonitor:
        """Dummy MempoolMonitor - web3 not installed"""
        def __init__(self, *args, **kwargs):
            pass
    
    MempoolMonitorV3 = MempoolMonitor
    
    class FlashbotsExecutor:
        """Dummy FlashbotsExecutor - web3 not installed"""
        def __init__(self, *args, **kwargs):
            pass
    
    DirectExecutor = FlashbotsExecutor
    
    class SniperStrategy:
        """Dummy SniperStrategy - web3 not installed"""
        def __init__(self, *args, **kwargs):
            pass


__all__ = [
    "SniperBot",
    "ContractAnalyzer",
    "MempoolMonitor",
    "MempoolMonitorV3",
    "FlashbotsExecutor",
    "DirectExecutor",
    "SniperStrategy",
    "WEB3_AVAILABLE",
]
