"""
Multi-DEX Aggregator - Trouve le meilleur prix sur tous les DEX.

Agrège les prix de :
1. Uniswap V2/V3
2. SushiSwap
3. PancakeSwap
4. QuickSwap
5. Curve
6. Balancer
7. 1inch (meta-aggregator)
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from web3 import Web3
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class DEXQuote:
    """Quote d'un DEX."""
    dex_name: str
    chain: str
    price: float
    amount_out: float
    gas_estimate: float
    gas_cost_usd: float
    net_amount: float  # amount_out - gas_cost
    router_address: str
    path: List[str]
    slippage: float


@dataclass  
class BestRoute:
    """Meilleure route trouvée."""
    best_quote: DEXQuote
    all_quotes: List[DEXQuote]
    savings_vs_worst: float
    savings_percent: float


class DEXAggregator:
    """Agrège les prix de plusieurs DEX pour trouver le meilleur."""
    
    # DEX Routers par chain
    DEX_ROUTERS = {
        "ethereum": {
            "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
            "sushiswap": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        },
        "bsc": {
            "pancakeswap": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
            "biswap": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
        },
        "arbitrum": {
            "uniswap_v2": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
            "sushiswap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            "camelot": "0xc873fEcbd354f5A56E00E710B90EF4201db2448d",
        },
        "base": {
            "uniswap_v2": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
            "aerodrome": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        },
        "polygon": {
            "quickswap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
            "sushiswap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        },
    }
    
    # WETH/Native token addresses
    WRAPPED_NATIVE = {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "base": "0x4200000000000000000000000000000000000006",
        "polygon": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    }
    
    # 1inch API
    ONEINCH_API = "https://api.1inch.dev/swap/v6.0"
    
    # Gas prices (gwei) - updated dynamically
    GAS_PRICES = {
        "ethereum": 30,
        "bsc": 3,
        "arbitrum": 0.1,
        "base": 0.01,
        "polygon": 50,
    }
    
    # Native token prices (USD)
    NATIVE_PRICES = {
        "ethereum": 1900,
        "bsc": 600,
        "arbitrum": 1900,
        "base": 1900,
        "polygon": 0.5,
    }
    
    def __init__(self, web3_providers: Dict[str, Web3] = None):
        self.providers = web3_providers or {}
        self._quote_cache: Dict[str, DEXQuote] = {}
        self._cache_ttl = 10  # 10 seconds
        
    async def get_best_price(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        chain: str = "ethereum",
        slippage: float = 1.0
    ) -> BestRoute:
        """
        Trouve le meilleur prix sur tous les DEX.
        
        Args:
            token_in: Adresse token d'entrée (ou "ETH" pour natif)
            token_out: Adresse token de sortie
            amount_in: Montant en token_in
            chain: Blockchain
            slippage: Slippage toléré en %
            
        Returns:
            BestRoute avec le meilleur quote et alternatives
        """
        quotes = []
        
        # Get quotes from all DEXes in parallel
        tasks = []
        
        # 1inch aggregator (best option)
        tasks.append(self._get_1inch_quote(token_in, token_out, amount_in, chain, slippage))
        
        # Individual DEX quotes
        if chain in self.DEX_ROUTERS:
            for dex_name, router in self.DEX_ROUTERS[chain].items():
                tasks.append(self._get_dex_quote(
                    dex_name, router, token_in, token_out, amount_in, chain, slippage
                ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, DEXQuote):
                quotes.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Quote error: {result}")
        
        if not quotes:
            raise ValueError(f"No quotes available for {token_in} -> {token_out} on {chain}")
        
        # Sort by net amount (after gas)
        quotes.sort(key=lambda q: q.net_amount, reverse=True)
        
        best = quotes[0]
        worst = quotes[-1]
        
        savings = best.net_amount - worst.net_amount if len(quotes) > 1 else 0
        savings_percent = (savings / worst.net_amount * 100) if worst.net_amount > 0 else 0
        
        route = BestRoute(
            best_quote=best,
            all_quotes=quotes,
            savings_vs_worst=savings,
            savings_percent=savings_percent
        )
        
        logger.info(f"🔄 Best price for {amount_in} on {chain}:")
        logger.info(f"   Best: {best.dex_name} -> {best.amount_out:.6f} (net: {best.net_amount:.6f})")
        if len(quotes) > 1:
            logger.info(f"   Savings vs worst: {savings:.6f} ({savings_percent:.1f}%)")
        
        return route
    
    async def _get_1inch_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        chain: str,
        slippage: float
    ) -> Optional[DEXQuote]:
        """Get quote from 1inch API."""
        chain_ids = {
            "ethereum": 1,
            "bsc": 56,
            "arbitrum": 42161,
            "base": 8453,
            "polygon": 137,
        }
        
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return None
        
        # Handle native token
        if token_in.upper() in ["ETH", "BNB", "MATIC"]:
            token_in = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Convert amount to wei (assuming 18 decimals)
                amount_wei = int(amount_in * 10**18)
                
                url = f"{self.ONEINCH_API}/{chain_id}/quote"
                params = {
                    "src": token_in,
                    "dst": token_out,
                    "amount": str(amount_wei),
                }
                
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        amount_out = int(data.get("dstAmount", 0)) / 10**18
                        gas = data.get("gas", 200000)
                        
                        gas_price_gwei = self.GAS_PRICES.get(chain, 10)
                        gas_cost_eth = (gas * gas_price_gwei) / 10**9
                        gas_cost_usd = gas_cost_eth * self.NATIVE_PRICES.get(chain, 1900)
                        
                        return DEXQuote(
                            dex_name="1inch",
                            chain=chain,
                            price=amount_out / amount_in if amount_in > 0 else 0,
                            amount_out=amount_out,
                            gas_estimate=gas,
                            gas_cost_usd=gas_cost_usd,
                            net_amount=amount_out - (gas_cost_usd / self.NATIVE_PRICES.get(chain, 1)),
                            router_address=data.get("tx", {}).get("to", ""),
                            path=data.get("protocols", []),
                            slippage=slippage
                        )
                    return None
        except Exception as e:
            logger.debug(f"1inch quote error: {e}")
            return None
    
    async def _get_dex_quote(
        self,
        dex_name: str,
        router_address: str,
        token_in: str,
        token_out: str,
        amount_in: float,
        chain: str,
        slippage: float
    ) -> Optional[DEXQuote]:
        """Get quote from a specific DEX router."""
        if chain not in self.providers:
            return None
            
        w3 = self.providers[chain]
        
        try:
            # Handle native token
            wrapped = self.WRAPPED_NATIVE.get(chain)
            if token_in.upper() in ["ETH", "BNB", "MATIC", "NATIVE"]:
                token_in = wrapped
            
            # Router ABI for getAmountsOut
            router_abi = [
                {
                    "name": "getAmountsOut",
                    "type": "function",
                    "inputs": [
                        {"name": "amountIn", "type": "uint256"},
                        {"name": "path", "type": "address[]"}
                    ],
                    "outputs": [
                        {"name": "amounts", "type": "uint256[]"}
                    ]
                }
            ]
            
            router = w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=router_abi
            )
            
            # Build path
            path = [
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out)
            ]
            
            amount_in_wei = int(amount_in * 10**18)
            
            # Get amounts out
            amounts = router.functions.getAmountsOut(amount_in_wei, path).call()
            amount_out = amounts[-1] / 10**18
            
            # Estimate gas
            gas_estimate = 150000  # Typical swap gas
            gas_price_gwei = self.GAS_PRICES.get(chain, 10)
            gas_cost_eth = (gas_estimate * gas_price_gwei) / 10**9
            gas_cost_usd = gas_cost_eth * self.NATIVE_PRICES.get(chain, 1900)
            
            return DEXQuote(
                dex_name=dex_name,
                chain=chain,
                price=amount_out / amount_in if amount_in > 0 else 0,
                amount_out=amount_out,
                gas_estimate=gas_estimate,
                gas_cost_usd=gas_cost_usd,
                net_amount=amount_out - (gas_cost_usd / self.NATIVE_PRICES.get(chain, 1)),
                router_address=router_address,
                path=path,
                slippage=slippage
            )
            
        except Exception as e:
            logger.debug(f"{dex_name} quote error: {e}")
            return None
    
    async def update_gas_prices(self):
        """Update gas prices from networks."""
        for chain, w3 in self.providers.items():
            try:
                gas_price = w3.eth.gas_price
                self.GAS_PRICES[chain] = gas_price / 10**9  # Convert to gwei
            except Exception as e:
                logger.debug(f"Gas price update error for {chain}: {e}")
    
    def get_supported_dexes(self, chain: str) -> List[str]:
        """Get list of supported DEXes for a chain."""
        dexes = list(self.DEX_ROUTERS.get(chain, {}).keys())
        dexes.append("1inch")  # Always available
        return dexes


# Singleton
_aggregator: Optional[DEXAggregator] = None


def get_dex_aggregator(providers: Dict[str, Web3] = None) -> DEXAggregator:
    """Get or create DEX aggregator singleton."""
    global _aggregator
    if _aggregator is None:
        _aggregator = DEXAggregator(providers)
    return _aggregator
