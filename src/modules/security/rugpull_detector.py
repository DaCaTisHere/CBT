"""
Rug Pull Detector - Analyse les tokens pour détecter les risques de rug pull.

Vérifie :
1. Concentration des holders (whale dominance)
2. Liquidité verrouillée ou non
3. Contrat renoncé ou non
4. Âge du token
5. Historique du créateur
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from web3 import Web3
import aiohttp

logger = logging.getLogger(__name__)


class RugPullDetector:
    """Détecte les risques de rug pull."""
    
    # APIs
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
    GOPLUS_API = "https://api.gopluslabs.com/api/v1/token_security"
    
    # Thresholds
    MAX_TOP_HOLDER_PERCENT = 50  # Max % pour le top holder
    MAX_TOP_10_PERCENT = 80  # Max % pour top 10 holders
    MIN_LIQUIDITY_USD = 5000  # Minimum liquidité
    MIN_TOKEN_AGE_HOURS = 1  # Âge minimum du token
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def analyze(
        self, 
        token_address: str, 
        chain: str = "ethereum"
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Analyse un token pour les risques de rug pull.
        
        Returns:
            Tuple[int, Dict]: (risk_score 0-100, details)
        """
        cache_key = f"{chain}:{token_address.lower()}"
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached["risk_score"], cached["details"]
        
        details = {
            "token": token_address,
            "chain": chain,
            "checks": {},
            "risk_factors": [],
            "safety_factors": [],
        }
        
        risk_score = 0
        
        try:
            # Run all checks in parallel
            results = await asyncio.gather(
                self._check_dexscreener(token_address, chain),
                self._check_goplus_security(token_address, chain),
                return_exceptions=True
            )
            
            # Process DexScreener data
            if isinstance(results[0], dict) and not results[0].get("error"):
                dex_data = results[0]
                details["checks"]["dexscreener"] = dex_data
                
                # Check liquidity
                liquidity = dex_data.get("liquidity_usd", 0)
                if liquidity < self.MIN_LIQUIDITY_USD:
                    risk_score += 25
                    details["risk_factors"].append(f"Low liquidity: ${liquidity:,.0f}")
                elif liquidity > 50000:
                    details["safety_factors"].append(f"Good liquidity: ${liquidity:,.0f}")
                
                # Check token age
                created_at = dex_data.get("created_at")
                if created_at:
                    age_hours = (datetime.now() - created_at).total_seconds() / 3600
                    if age_hours < self.MIN_TOKEN_AGE_HOURS:
                        risk_score += 20
                        details["risk_factors"].append(f"Very new token: {age_hours:.1f}h old")
                    elif age_hours > 24:
                        details["safety_factors"].append(f"Token age: {age_hours:.0f}h")
                
                # Check price change (pump and dump indicator)
                price_change_24h = dex_data.get("price_change_24h", 0)
                if price_change_24h > 1000:
                    risk_score += 15
                    details["risk_factors"].append(f"Extreme pump: +{price_change_24h:.0f}%")
                elif price_change_24h < -50:
                    risk_score += 20
                    details["risk_factors"].append(f"Major dump: {price_change_24h:.0f}%")
                    
            # Process GoPlus security data
            if isinstance(results[1], dict) and not results[1].get("error"):
                security = results[1]
                details["checks"]["goplus"] = security
                
                # Owner not renounced
                if not security.get("is_open_source"):
                    risk_score += 15
                    details["risk_factors"].append("Contract not verified/open source")
                else:
                    details["safety_factors"].append("Contract verified")
                    
                if security.get("owner_address") and security["owner_address"] != "0x0000000000000000000000000000000000000000":
                    risk_score += 10
                    details["risk_factors"].append("Ownership not renounced")
                else:
                    details["safety_factors"].append("Ownership renounced")
                
                # Can mint more tokens
                if security.get("is_mintable"):
                    risk_score += 20
                    details["risk_factors"].append("Token is mintable")
                    
                # High holder concentration
                top_holder_percent = security.get("holder_percent", 0)
                if top_holder_percent > self.MAX_TOP_HOLDER_PERCENT:
                    risk_score += 25
                    details["risk_factors"].append(f"Top holder owns {top_holder_percent:.1f}%")
                    
                # Check if LP is locked
                if security.get("lp_holders"):
                    lp_locked = any(
                        h.get("is_locked") 
                        for h in security.get("lp_holders", [])
                    )
                    if lp_locked:
                        risk_score -= 10  # Reduce risk
                        details["safety_factors"].append("Liquidity is locked")
                    else:
                        risk_score += 20
                        details["risk_factors"].append("Liquidity NOT locked")
                        
                # Creator history
                if security.get("creator_address"):
                    creator_percent = security.get("creator_percent", 0)
                    if creator_percent > 20:
                        risk_score += 15
                        details["risk_factors"].append(f"Creator holds {creator_percent:.1f}%")
            
            # Cap risk score
            risk_score = max(0, min(100, risk_score))
            
            # Determine risk level
            if risk_score >= 70:
                details["risk_level"] = "EXTREME"
                details["recommendation"] = "DO NOT BUY"
            elif risk_score >= 50:
                details["risk_level"] = "HIGH"
                details["recommendation"] = "AVOID"
            elif risk_score >= 30:
                details["risk_level"] = "MEDIUM"
                details["recommendation"] = "CAUTION"
            else:
                details["risk_level"] = "LOW"
                details["recommendation"] = "OK TO TRADE"
            
            # Cache result
            self._cache[cache_key] = {
                "risk_score": risk_score,
                "details": details,
            }
            
            # Log result
            if risk_score >= 50:
                logger.warning(f"⚠️ RUG RISK {details['risk_level']}: {token_address}")
                logger.warning(f"   Risk score: {risk_score}/100")
                for factor in details["risk_factors"]:
                    logger.warning(f"   🚩 {factor}")
            else:
                logger.info(f"✅ Token OK: {token_address} (risk: {risk_score}/100)")
                
            return risk_score, details
            
        except Exception as e:
            logger.error(f"Rug pull analysis error for {token_address}: {e}")
            details["error"] = str(e)
            return 50, details  # Medium risk on error
    
    async def _check_dexscreener(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Récupère les données de DexScreener."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.DEXSCREENER_API}/{token_address}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get("pairs", [])
                        
                        if not pairs:
                            return {"error": "No pairs found"}
                        
                        # Get the main pair (highest liquidity)
                        main_pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
                        
                        created_at = None
                        if main_pair.get("pairCreatedAt"):
                            created_at = datetime.fromtimestamp(main_pair["pairCreatedAt"] / 1000)
                        
                        return {
                            "liquidity_usd": main_pair.get("liquidity", {}).get("usd", 0),
                            "volume_24h": main_pair.get("volume", {}).get("h24", 0),
                            "price_change_24h": main_pair.get("priceChange", {}).get("h24", 0),
                            "txns_24h": main_pair.get("txns", {}).get("h24", {}),
                            "created_at": created_at,
                            "dex": main_pair.get("dexId"),
                            "pair_address": main_pair.get("pairAddress"),
                        }
                    return {"error": f"API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _check_goplus_security(
        self, 
        token_address: str, 
        chain: str
    ) -> Dict[str, Any]:
        """Vérifie la sécurité via GoPlus."""
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
                url = f"{self.GOPLUS_API}/{chain_id}?contract_addresses={token_address}"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get("result", {}).get(token_address.lower(), {})
                        
                        # Parse holder concentration
                        holders = result.get("holders", [])
                        top_holder_percent = 0
                        if holders:
                            top_holder_percent = float(holders[0].get("percent", 0)) * 100
                        
                        return {
                            "is_open_source": result.get("is_open_source") == "1",
                            "owner_address": result.get("owner_address"),
                            "is_mintable": result.get("is_mintable") == "1",
                            "holder_percent": top_holder_percent,
                            "lp_holders": result.get("lp_holders", []),
                            "creator_address": result.get("creator_address"),
                            "creator_percent": float(result.get("creator_percent", 0)) * 100,
                            "total_supply": result.get("total_supply"),
                            "holder_count": result.get("holder_count"),
                        }
                    return {"error": f"API returned {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def quick_check(
        self, 
        token_address: str, 
        chain: str = "ethereum"
    ) -> bool:
        """
        Quick check - retourne True si le token semble safe.
        
        Returns:
            bool: True if safe to trade, False if risky
        """
        risk_score, _ = await self.analyze(token_address, chain)
        return risk_score < 50


# Singleton instance
_detector: Optional[RugPullDetector] = None


def get_rugpull_detector() -> RugPullDetector:
    """Get or create rug pull detector singleton."""
    global _detector
    if _detector is None:
        _detector = RugPullDetector()
    return _detector
