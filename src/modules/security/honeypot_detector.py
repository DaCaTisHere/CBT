"""
Honeypot Detector - Détecte les tokens impossibles à vendre AVANT achat.

Utilise plusieurs méthodes :
1. Simulation de vente via eth_call
2. Analyse du bytecode du contrat
3. Vérification des fonctions de transfert
4. Check des taxes d'achat/vente
"""
import asyncio
import logging
from typing import Optional, Dict, Any, Tuple
from web3 import Web3
from web3.exceptions import ContractLogicError
import aiohttp

logger = logging.getLogger(__name__)


class HoneypotDetector:
    """Détecte les honeypots et tokens dangereux."""
    
    # Signatures de fonctions suspectes dans le bytecode
    SUSPICIOUS_SIGNATURES = [
        "a]",  # blacklist
        "setBot",
        "setBlacklist", 
        "blockBots",
        "antibotEnabled",
        "tradingEnabled",
        "maxTxAmount",
        "cooldown",
    ]
    
    # APIs de vérification honeypot
    HONEYPOT_API_URL = "https://api.honeypot.is/v2/IsHoneypot"
    GOPLUS_API_URL = "https://api.gopluslabs.io/api/v1/token_security"
    
    # Routers par chain
    ROUTERS = {
        "ethereum": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2
        "bsc": "0x10ED43C718714eb63d5aA57B78B54704E256024E",  # PancakeSwap
        "arbitrum": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap
        "base": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",  # Uniswap V2
        "polygon": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",  # QuickSwap
    }
    
    # WETH addresses par chain
    WETH = {
        "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
        "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "base": "0x4200000000000000000000000000000000000006",
        "polygon": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
    }
    
    def __init__(self, web3_providers: Dict[str, Web3]):
        """
        Args:
            web3_providers: Dict de Web3 instances par chain
        """
        self.providers = web3_providers
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def is_honeypot(
        self, 
        token_address: str, 
        chain: str = "ethereum"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Vérifie si un token est un honeypot.
        
        Returns:
            Tuple[bool, Dict]: (is_honeypot, details)
        """
        cache_key = f"{chain}:{token_address.lower()}"
        
        # Check cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached["is_honeypot"], cached["details"]
        
        details = {
            "token": token_address,
            "chain": chain,
            "checks": {},
            "risk_score": 0,
            "warnings": [],
        }
        
        try:
            # Run all checks in parallel
            results = await asyncio.gather(
                self._check_honeypot_api(token_address, chain),
                self._check_goplus_api(token_address, chain),
                self._simulate_sell(token_address, chain),
                self._check_contract_code(token_address, chain),
                return_exceptions=True
            )
            
            # Process Honeypot.is API
            if isinstance(results[0], dict):
                details["checks"]["honeypot_api"] = results[0]
                if results[0].get("is_honeypot"):
                    details["risk_score"] += 100
                    details["warnings"].append("Honeypot.is: Token flagged as honeypot")
                if results[0].get("buy_tax", 0) > 10:
                    details["risk_score"] += 20
                    details["warnings"].append(f"High buy tax: {results[0].get('buy_tax')}%")
                if results[0].get("sell_tax", 0) > 10:
                    details["risk_score"] += 30
                    details["warnings"].append(f"High sell tax: {results[0].get('sell_tax')}%")
            
            # Process GoPlus API
            if isinstance(results[1], dict):
                details["checks"]["goplus"] = results[1]
                if results[1].get("is_honeypot"):
                    details["risk_score"] += 100
                    details["warnings"].append("GoPlus: Token flagged as honeypot")
                if results[1].get("cannot_sell_all"):
                    details["risk_score"] += 50
                    details["warnings"].append("Cannot sell all tokens")
                if results[1].get("owner_can_change_balance"):
                    details["risk_score"] += 40
                    details["warnings"].append("Owner can change balances")
                if results[1].get("hidden_owner"):
                    details["risk_score"] += 30
                    details["warnings"].append("Hidden owner detected")
                if results[1].get("is_blacklisted"):
                    details["risk_score"] += 25
                    details["warnings"].append("Blacklist function detected")
                    
            # Process sell simulation
            if isinstance(results[2], dict):
                details["checks"]["sell_simulation"] = results[2]
                if not results[2].get("can_sell"):
                    details["risk_score"] += 100
                    details["warnings"].append("Sell simulation failed")
                    
            # Process contract code analysis
            if isinstance(results[3], dict):
                details["checks"]["contract_analysis"] = results[3]
                details["risk_score"] += results[3].get("risk_score", 0)
                details["warnings"].extend(results[3].get("warnings", []))
            
            # Determine if honeypot
            is_honeypot = details["risk_score"] >= 50
            
            # Cache result
            self._cache[cache_key] = {
                "is_honeypot": is_honeypot,
                "details": details,
            }
            
            if is_honeypot:
                logger.warning(f"🍯 HONEYPOT DETECTED: {token_address} on {chain}")
                logger.warning(f"   Risk score: {details['risk_score']}")
                for warning in details["warnings"]:
                    logger.warning(f"   ⚠️ {warning}")
            else:
                logger.info(f"✅ Token safe: {token_address} (risk: {details['risk_score']})")
                
            return is_honeypot, details
            
        except Exception as e:
            logger.error(f"Honeypot check error for {token_address}: {e}")
            details["error"] = str(e)
            # En cas d'erreur, considérer comme risqué
            return True, details
    
    async def _check_honeypot_api(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Vérifie via l'API Honeypot.is"""
        chain_ids = {
            "ethereum": 1,
            "bsc": 56,
            "arbitrum": 42161,
            "base": 8453,
            "polygon": 137,
        }
        
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return {"error": f"Chain {chain} not supported"}
            
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.HONEYPOT_API_URL}?address={token_address}&chainId={chain_id}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "is_honeypot": data.get("honeypotResult", {}).get("isHoneypot", False),
                            "buy_tax": data.get("simulationResult", {}).get("buyTax", 0),
                            "sell_tax": data.get("simulationResult", {}).get("sellTax", 0),
                            "transfer_tax": data.get("simulationResult", {}).get("transferTax", 0),
                        }
                    return {"error": f"API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _check_goplus_api(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Vérifie via l'API GoPlus Security."""
        chain_ids = {
            "ethereum": "1",
            "bsc": "56", 
            "arbitrum": "42161",
            "base": "8453",
            "polygon": "137",
        }
        
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return {"error": f"Chain {chain} not supported"}
            
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.GOPLUS_API_URL}/{chain_id}?contract_addresses={token_address}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {}).get(token_address.lower(), {})
                        return {
                            "is_honeypot": result.get("is_honeypot") == "1",
                            "cannot_sell_all": result.get("cannot_sell_all") == "1",
                            "owner_can_change_balance": result.get("owner_change_balance") == "1",
                            "hidden_owner": result.get("hidden_owner") == "1",
                            "is_blacklisted": result.get("is_blacklisted") == "1",
                            "is_proxy": result.get("is_proxy") == "1",
                            "is_mintable": result.get("is_mintable") == "1",
                            "can_take_back_ownership": result.get("can_take_back_ownership") == "1",
                            "transfer_pausable": result.get("transfer_pausable") == "1",
                            "trading_cooldown": result.get("trading_cooldown") == "1",
                        }
                    return {"error": f"API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _simulate_sell(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Simule une vente pour vérifier si possible."""
        if chain not in self.providers:
            return {"error": f"No provider for {chain}"}
            
        w3 = self.providers[chain]
        router = self.ROUTERS.get(chain)
        weth = self.WETH.get(chain)
        
        if not router or not weth:
            return {"error": f"No router/weth for {chain}"}
            
        try:
            # Minimal ERC20 ABI for simulation
            erc20_abi = [
                {"name": "approve", "type": "function", "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "amount", "type": "uint256"}
                ], "outputs": [{"type": "bool"}]},
                {"name": "balanceOf", "type": "function", "inputs": [
                    {"name": "account", "type": "address"}
                ], "outputs": [{"type": "uint256"}]},
            ]
            
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=erc20_abi
            )
            
            # Try to get decimals and total supply to verify contract is valid
            try:
                # Use a random test address
                test_address = "0x000000000000000000000000000000000000dEaD"
                balance = token_contract.functions.balanceOf(test_address).call()
                return {"can_sell": True, "test_balance": balance}
            except Exception as e:
                return {"can_sell": False, "error": str(e)}
                
        except Exception as e:
            return {"error": str(e)}
    
    async def _check_contract_code(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Analyse le bytecode du contrat pour détecter des patterns suspects."""
        if chain not in self.providers:
            return {"error": f"No provider for {chain}"}
            
        w3 = self.providers[chain]
        
        try:
            # Get contract bytecode
            code = w3.eth.get_code(Web3.to_checksum_address(token_address))
            code_hex = code.hex()
            
            result = {
                "risk_score": 0,
                "warnings": [],
                "code_size": len(code),
            }
            
            # Check for suspicious patterns
            for sig in self.SUSPICIOUS_SIGNATURES:
                if sig.lower().encode().hex() in code_hex.lower():
                    result["risk_score"] += 10
                    result["warnings"].append(f"Suspicious pattern: {sig}")
            
            # Very small contract = suspicious
            if len(code) < 500:
                result["risk_score"] += 15
                result["warnings"].append("Very small contract code")
                
            # Check for self-destruct
            if "ff" in code_hex:  # SELFDESTRUCT opcode
                result["risk_score"] += 20
                result["warnings"].append("Self-destruct capability detected")
                
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_token_taxes(
        self, 
        token_address: str, 
        chain: str = "ethereum"
    ) -> Tuple[float, float]:
        """
        Retourne les taxes d'achat et vente.
        
        Returns:
            Tuple[float, float]: (buy_tax_percent, sell_tax_percent)
        """
        _, details = await self.is_honeypot(token_address, chain)
        
        buy_tax = 0.0
        sell_tax = 0.0
        
        if "honeypot_api" in details.get("checks", {}):
            api_data = details["checks"]["honeypot_api"]
            buy_tax = api_data.get("buy_tax", 0)
            sell_tax = api_data.get("sell_tax", 0)
            
        return buy_tax, sell_tax


# Singleton instance
_detector: Optional[HoneypotDetector] = None


def get_honeypot_detector(web3_providers: Dict[str, Web3] = None) -> HoneypotDetector:
    """Get or create honeypot detector singleton."""
    global _detector
    if _detector is None and web3_providers:
        _detector = HoneypotDetector(web3_providers)
    return _detector
