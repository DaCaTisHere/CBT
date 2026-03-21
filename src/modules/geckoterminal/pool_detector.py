"""
Pool Detector - Detects new and trending pools for trading

Scans multiple chains for:
- Newly created pools (sniper opportunities)
- Trending pools (momentum plays)
- High volume pools (liquidity confirmation)
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from src.modules.geckoterminal.gecko_client import GeckoTerminalClient, Pool
from src.modules.geckoterminal.dexscreener_client import DexScreenerClient
from src.modules.security import honeypot_detector
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PoolSignal:
    """Trading signal from pool detection"""
    pool: Pool
    signal_type: str  # "new_pool", "trending", "volume_spike"
    score: float  # 0-100
    reasons: List[str]
    timestamp: datetime


class PoolDetector:
    """
    Detects tradeable pools across multiple chains
    
    Strategies:
    1. NEW POOL: Early entry on newly created pools
    2. TRENDING: Momentum on pools gaining volume
    3. VOLUME SPIKE: Sudden liquidity increase
    """
    
    # ONLY chains where wallet has actual funds for trading
    # BSC: 0.08 BNB (~$53), Base: 0.027 ETH (~$56)
    # Don't waste API calls on chains with 0 balance
    ALL_CHAINS = ["bsc", "base"]
    
    # SNIPER MODE - Aggressive filters for new tokens
    # Lower thresholds to catch tokens early
    MIN_LIQUIDITY_USD = 5000       # $5k minimum (catch early)
    MAX_LIQUIDITY_USD = 2000000    # $2M max (avoid established tokens)
    MIN_VOLUME_24H = 1000          # $1k minimum (very new tokens)
    MIN_TRANSACTIONS_24H = 20      # At least 20 trades (new but active)
    MIN_BUY_RATIO = 0.5            # At least 50% buys (bullish)
    
    # Filters for trending
    MIN_PRICE_CHANGE_24H = 5       # At least +5% in 24h (catch early momentum)
    MAX_PRICE_CHANGE_24H = 1000    # Allow bigger pumps
    
    NEW_TOKEN_TAKE_PROFIT_1 = 30
    NEW_TOKEN_TAKE_PROFIT_2 = 75
    NEW_TOKEN_TAKE_PROFIT_3 = 150
    NEW_TOKEN_STOP_LOSS = 20
    NEW_TOKEN_MAX_HOLD_HOURS = 0.5
    
    SEARCH_TERMS = [
        "new", "launch", "fair", "meme", "pepe", "doge", "moon",
        "ai", "gpt", "sol", "bnb", "base", "cat", "frog",
        "pump", "gem", "alpha", "dao", "defi", "nft",
    ]
    
    def __init__(self):
        self.logger = logger
        self.client = GeckoTerminalClient()  # Fallback
        self.dexscreener = DexScreenerClient()  # Primary source
        self.is_running = False
        
        # Tracking
        self.seen_pools: Dict[str, datetime] = {}  # pool_address -> first_seen
        self.signals: List[PoolSignal] = []
        self.signal_callbacks: List[Callable] = []
        
        # Chain rotation for GeckoTerminal fallback
        self._chain_index = 0
        self._chains_per_cycle = 1
        
        # Search term rotation
        self._search_index = 0
        
        # Stats
        self.pools_scanned = 0
        self.signals_generated = 0
        
    async def initialize(self):
        """Initialize the detector"""
        await self.client.initialize()
        await self.dexscreener.initialize()
        self.logger.info("[POOL] Pool Detector initialized (DexScreener primary + GeckoTerminal fallback)")
        
    async def close(self):
        """Close the detector"""
        self.is_running = False
        await self.client.close()
        await self.dexscreener.close()
        
    def on_signal(self, callback: Callable):
        """Register callback for new signals"""
        self.signal_callbacks.append(callback)
        
    async def _emit_signal(self, signal: PoolSignal):
        """Emit signal to all callbacks"""
        self.signals.append(signal)
        self.signals_generated += 1
        
        for callback in self.signal_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(signal)
                else:
                    callback(signal)
            except Exception as e:
                self.logger.error(f"[POOL] Callback error: {e}")
                
    def _clean_seen_pools(self):
        """Remove old entries from seen_pools to allow re-evaluation"""
        now = datetime.now(timezone.utc)
        expired = [
            addr for addr, seen_at in self.seen_pools.items()
            if (now - seen_at) > timedelta(minutes=30)
        ]
        if expired:
            for addr in expired:
                del self.seen_pools[addr]
            self.logger.info(f"[POOL] 🧹 Cleaned {len(expired)} old cache entries ({len(self.seen_pools)} remaining)")
    
    def _get_next_search_term(self) -> str:
        """Rotate through search terms for discovery"""
        term = self.SEARCH_TERMS[self._search_index % len(self.SEARCH_TERMS)]
        self._search_index += 1
        return term
    
    async def _process_pools(self, pools: List, source: str, signal_type: str = "new_pool", max_process: int = 10):
        """Process a batch of pools: enrich, score, and emit signals"""
        relevant = [p for p in pools if p.network in self.ALL_CHAINS]
        if not relevant:
            return 0
        
        self.logger.info(f"[POOL] {source}: {len(pools)} total, {len(relevant)} on funded chains (BSC/Base)")
        new_signals = 0
        
        for pool in relevant[:max_process]:
            if pool.address in self.seen_pools:
                continue
            
            original_address = pool.address
            pool = await self.dexscreener.enrich_pool(pool)
            await asyncio.sleep(0.5)
            
            self.seen_pools[original_address] = datetime.now(timezone.utc)
            token_addr = pool.token_address or pool.address
            if token_addr != original_address:
                self.seen_pools[token_addr] = datetime.now(timezone.utc)
            self.pools_scanned += 1
            
            # Score based on signal type
            if signal_type == "trending":
                score, reasons = self._score_trending_pool(pool)
                is_sniper = False
                min_score = 60  # Lower for trending (was 70)
            else:
                score, reasons, is_sniper = self._score_new_pool(pool)
                min_score = 45 if is_sniper else 60
            
            if score >= min_score:
                safety_check = await honeypot_detector.check_token(pool.token_address or pool.address, pool.network)
                if not safety_check["is_safe"]:
                    self.logger.warning(
                        f"[POOL] 🍯 BLOCKED {pool.base_token} on {pool.network.upper()}: "
                        f"{safety_check['reasons']} (risk={safety_check['risk_level']})"
                    )
                    continue

                actual_type = "sniper" if is_sniper else signal_type
                signal = PoolSignal(
                    pool=pool,
                    signal_type=actual_type,
                    score=score,
                    reasons=reasons,
                    timestamp=datetime.now(timezone.utc)
                )

                emoji = {"sniper": "🎯", "new_pool": "🆕", "trending": "🔥"}.get(actual_type, "📡")
                self.logger.info(f"[POOL] {emoji} {actual_type.upper()} on {pool.network.upper()}: {pool.base_token}")
                self.logger.info(f"[POOL]    Price: ${pool.price_usd:.8f} | Liq: ${pool.liquidity_usd:,.0f} | Vol: ${pool.volume_24h:,.0f}")
                self.logger.info(f"[POOL]    Score: {score:.0f}/100 | {', '.join(reasons[:3])}")
                self.logger.info(f"[POOL]    Safety: {safety_check['risk_level']} | Tax: buy={safety_check['details'].get('buy_tax', 0)*100:.1f}% sell={safety_check['details'].get('sell_tax', 0)*100:.1f}%")

                await self._emit_signal(signal)
                new_signals += 1
            else:
                if pool.liquidity_usd > 0:
                    self.logger.debug(f"[POOL] ⏭️ Skip {pool.base_token}: score {score:.0f} < {min_score} (liq=${pool.liquidity_usd:,.0f})")
        
        return new_signals
    
    async def start(self):
        """Start pool detection loop - AGGRESSIVE multi-source scanning"""
        self.is_running = True
        self.logger.info("[POOL] 🎯 SNIPER MODE v2 - Aggressive multi-source detection")
        self.logger.info(f"[POOL] FUNDED chains only: {', '.join(self.ALL_CHAINS)}")
        self.logger.info(f"[POOL] Sources: DexScreener profiles + boosts + top + search + GeckoTerminal fallback")
        
        # Short initial delay
        self.logger.info("[POOL] Waiting 10s before first scan...")
        await asyncio.sleep(10)
        
        cycle = 0
        while self.is_running:
            try:
                cycle += 1
                cycle_signals = 0
                
                # ====== CLEAN OLD CACHE ======
                self._clean_seen_pools()
                
                # ====== SOURCE 1: DexScreener Latest Profiles ======
                self.logger.info("[POOL] 🔍 Scanning DexScreener profiles...")
                new_tokens = await self.dexscreener.get_latest_token_profiles()
                if new_tokens:
                    cycle_signals += await self._process_pools(new_tokens, "Profiles", "new_pool")
                
                await asyncio.sleep(2)
                
                # ====== SOURCE 2: DexScreener Latest Boosted ======
                boosted = await self.dexscreener.get_latest_boosted_tokens()
                if boosted:
                    cycle_signals += await self._process_pools(boosted, "Boosted", "trending", max_process=8)
                
                await asyncio.sleep(2)
                
                # ====== SOURCE 3: DexScreener TOP Boosted (different set) ======
                top_boosted = await self.dexscreener.get_top_boosted_tokens()
                if top_boosted:
                    cycle_signals += await self._process_pools(top_boosted, "Top Boosted", "trending", max_process=8)
                
                await asyncio.sleep(2)
                
                # ====== SOURCE 4: DexScreener Search (rotating terms) ======
                # Every 3rd cycle, search for trending tokens on our chains
                if cycle % 3 == 0:
                    search_term = self._get_next_search_term()
                    self.logger.info(f"[POOL] 🔎 Searching DexScreener for '{search_term}'...")
                    search_results = await self.dexscreener.search_pairs_on_chain(
                        search_term, self.ALL_CHAINS
                    )
                    if search_results:
                        cycle_signals += await self._process_pools(
                            search_results, f"Search '{search_term}'", "new_pool", max_process=5
                        )
                    await asyncio.sleep(2)
                
                # ====== SOURCE 5: GeckoTerminal fallback (1 chain per cycle) ======
                chains_to_scan = self._get_next_chains()
                for chain in chains_to_scan:
                    await self._scan_new_pools(chain)
                    await asyncio.sleep(3)
                    await self._scan_trending_pools(chain)
                
                # Log cycle summary
                self.logger.info(
                    f"[POOL] Cycle #{cycle} done | "
                    f"New signals: {cycle_signals} | "
                    f"Total scanned: {self.pools_scanned} | "
                    f"Total signals: {self.signals_generated} | "
                    f"Cache: {len(self.seen_pools)}"
                )
                
                # Dynamic wait: shorter if we're finding signals, longer if not
                wait_time = 15 if cycle_signals > 0 else 25
                await asyncio.sleep(wait_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[POOL] Scan error: {e}")
                await asyncio.sleep(10)
    
    def _get_next_chains(self) -> List[str]:
        """Get next chains to scan (rotation for rate limit)"""
        chains = []
        for i in range(self._chains_per_cycle):
            idx = (self._chain_index + i) % len(self.ALL_CHAINS)
            chains.append(self.ALL_CHAINS[idx])
        
        # Advance rotation
        self._chain_index = (self._chain_index + self._chains_per_cycle) % len(self.ALL_CHAINS)
        return chains
                
    async def _scan_new_pools(self, chain: str):
        """Scan for new pools on a chain"""
        try:
            pools = await self.client.get_new_pools(chain, limit=20)
            self.pools_scanned += len(pools)
            if pools:
                self.logger.info(f"[POOL] ✅ Got {len(pools)} new pools on {chain.upper()}")
            
            for pool in pools:
                # Skip if already seen
                if pool.address in self.seen_pools:
                    continue
                    
                # Mark as seen
                self.seen_pools[pool.address] = datetime.now(timezone.utc)
                
                # Score the pool
                score, reasons, is_sniper_opportunity = self._score_new_pool(pool)
                
                # Lower threshold (50) for sniper opportunities
                min_score = 45 if is_sniper_opportunity else 60
                
                if score >= min_score:
                    safety_check = await honeypot_detector.check_token(pool.token_address or pool.address, pool.network)
                    if not safety_check["is_safe"]:
                        self.logger.warning(
                            f"[POOL] 🍯 BLOCKED {pool.base_token} on {chain.upper()}: "
                            f"{safety_check['reasons']} (risk={safety_check['risk_level']})"
                        )
                        continue

                    signal = PoolSignal(
                        pool=pool,
                        signal_type="sniper" if is_sniper_opportunity else "new_pool",
                        score=score,
                        reasons=reasons,
                        timestamp=datetime.now(timezone.utc)
                    )

                    emoji = "🎯" if is_sniper_opportunity else "🆕"
                    self.logger.info(f"[POOL] {emoji} {'SNIPER OPPORTUNITY' if is_sniper_opportunity else 'NEW POOL'} on {chain.upper()}")
                    self.logger.info(f"[POOL]    {pool.base_token}/{pool.quote_token} on {pool.dex}")
                    self.logger.info(f"[POOL]    Price: ${pool.price_usd:.8f} | Liq: ${pool.liquidity_usd:,.0f}")
                    self.logger.info(f"[POOL]    Score: {score:.0f}/100 | {', '.join(reasons)}")
                    if is_sniper_opportunity:
                        self.logger.info(f"[POOL]    💨 Quick trade: TP +{self.NEW_TOKEN_TAKE_PROFIT_1}%/+{self.NEW_TOKEN_TAKE_PROFIT_2}% | SL -{self.NEW_TOKEN_STOP_LOSS}%")

                    await self._emit_signal(signal)
                    
        except Exception as e:
            self.logger.error(f"[POOL] New pool scan error on {chain}: {e}")
            
    async def _scan_trending_pools(self, chain: str):
        """Scan for trending pools on a chain"""
        try:
            pools = await self.client.get_trending_pools(chain, limit=20)
            self.pools_scanned += len(pools)
            if pools:
                self.logger.info(f"[POOL] ✅ Got {len(pools)} trending pools on {chain.upper()}")
            
            for pool in pools:
                # Score the pool
                score, reasons = self._score_trending_pool(pool)
                
                # Avoid re-signaling same pool too often
                cache_key = f"trending_{pool.address}"
                if cache_key in self.seen_pools:
                    last_signal = self.seen_pools[cache_key]
                    if datetime.now(timezone.utc) - last_signal < timedelta(hours=1):
                        continue
                        
                if score >= 50:
                    safety_check = await honeypot_detector.check_token(pool.token_address or pool.address, pool.network)
                    if not safety_check["is_safe"]:
                        self.logger.warning(
                            f"[POOL] 🍯 BLOCKED trending {pool.base_token} on {chain.upper()}: "
                            f"{safety_check['reasons']} (risk={safety_check['risk_level']})"
                        )
                        continue

                    self.seen_pools[cache_key] = datetime.now(timezone.utc)

                    signal = PoolSignal(
                        pool=pool,
                        signal_type="trending",
                        score=score,
                        reasons=reasons,
                        timestamp=datetime.now(timezone.utc)
                    )

                    self.logger.info(f"[POOL] 🔥 TRENDING POOL on {chain.upper()}")
                    self.logger.info(f"[POOL]    {pool.base_token}/{pool.quote_token}")
                    self.logger.info(f"[POOL]    24h: {pool.price_change_24h:+.1f}% | Vol: ${pool.volume_24h:,.0f}")
                    self.logger.info(f"[POOL]    Score: {score:.0f}/100")

                    await self._emit_signal(signal)
                    
        except Exception as e:
            self.logger.error(f"[POOL] Trending scan error on {chain}: {e}")
            
    def _score_new_pool(self, pool: Pool) -> tuple[float, List[str], bool]:
        """
        Score a new pool for trading potential (SNIPER MODE)
        
        Returns:
            (score 0-100, list of reasons, is_sniper_opportunity)
        """
        score = 0
        reasons = []
        is_sniper = False
        
        # 1. Liquidity check (0-25 points)
        if pool.liquidity_usd >= self.MIN_LIQUIDITY_USD:
            if pool.liquidity_usd >= 100000:
                score += 25
                reasons.append("Strong liquidity")
            elif pool.liquidity_usd >= 50000:
                score += 20
                reasons.append("Good liquidity")
            elif pool.liquidity_usd >= 20000:
                score += 18
                reasons.append("Decent liquidity")
            else:
                score += 15
                reasons.append("Early liquidity")
                is_sniper = True  # Low liquidity = early entry opportunity
        else:
            return 0, ["Liquidity too low"], False
            
        # 2. Volume check (0-20 points)
        if pool.volume_24h >= self.MIN_VOLUME_24H:
            if pool.volume_24h >= 50000:
                score += 20
                reasons.append("High volume")
            elif pool.volume_24h >= 20000:
                score += 15
            elif pool.volume_24h >= 5000:
                score += 12
                is_sniper = True  # Lower volume = newer token
            else:
                score += 8
                is_sniper = True
        else:
            score += 5  # Still give some points for very new tokens
            is_sniper = True
            
        # 3. Transaction count (0-20 points) - adjusted for sniper
        if pool.transactions_24h >= self.MIN_TRANSACTIONS_24H:
            if pool.transactions_24h >= 200:
                score += 20
                reasons.append("Very active")
            elif pool.transactions_24h >= 100:
                score += 15
            elif pool.transactions_24h >= 50:
                score += 12
            else:
                score += 8
                is_sniper = True  # Low tx = very new
        else:
            score += 5  # Give points for being very new
            is_sniper = True
            reasons.append("Very new token")
                
        # 4. Buy/Sell ratio (0-25 points) - most important for sniper
        total_trades = pool.buys_24h + pool.sells_24h
        if total_trades > 0:
            buy_ratio = pool.buys_24h / total_trades
            if buy_ratio >= 0.7:
                score += 25
                reasons.append("🔥 Strong buying (70%+)")
                is_sniper = True  # Strong buying = sniper opportunity
            elif buy_ratio >= 0.6:
                score += 20
                reasons.append("Good buying pressure")
            elif buy_ratio >= self.MIN_BUY_RATIO:
                score += 12
            else:
                score -= 10
                reasons.append("More sells than buys")
                is_sniper = False  # Don't snipe if selling
                
        # 5. Price action (0-20 points)
        if 5 < pool.price_change_24h <= 50:
            score += 20
            reasons.append(f"🚀 +{pool.price_change_24h:.0f}% momentum")
            is_sniper = True
        elif 50 < pool.price_change_24h <= 200:
            score += 15
            reasons.append(f"+{pool.price_change_24h:.0f}% (watch for dump)")
        elif pool.price_change_24h > 200:
            score += 8
            reasons.append("Extreme pump (risky)")
            is_sniper = False  # Too late for snipe
        elif pool.price_change_24h < -10:
            score -= 15
            reasons.append("Dumping")
            is_sniper = False
            
        return max(0, min(100, score)), reasons, is_sniper
        
    def _score_trending_pool(self, pool: Pool) -> tuple[float, List[str]]:
        """
        Score a trending pool for momentum trading
        
        Returns:
            (score 0-100, list of reasons)
        """
        score = 0
        reasons = []
        
        if pool.liquidity_usd < 10000:
            return 0, ["Low liquidity"]
            
        # 2. Price change score (0-30 points)
        change = pool.price_change_24h
        if self.MIN_PRICE_CHANGE_24H <= change <= 50:
            score += 30
            reasons.append(f"Healthy pump +{change:.0f}%")
        elif 50 < change <= 100:
            score += 25
            reasons.append(f"Strong pump +{change:.0f}%")
        elif 100 < change <= self.MAX_PRICE_CHANGE_24H:
            score += 15
            reasons.append(f"Extreme pump +{change:.0f}% (caution)")
        elif change < self.MIN_PRICE_CHANGE_24H:
            return 0, ["Not enough momentum"]
        else:
            return 0, ["Pump too extreme"]
            
        # 3. Volume confirmation (0-25 points)
        if pool.volume_24h >= 100000:
            score += 25
            reasons.append("Very high volume")
        elif pool.volume_24h >= 50000:
            score += 20
        elif pool.volume_24h >= 20000:
            score += 15
        else:
            score += 5
            
        # 4. Liquidity score (0-20 points)
        if pool.liquidity_usd >= 500000:
            score += 20
            reasons.append("Deep liquidity")
        elif pool.liquidity_usd >= 200000:
            score += 15
        elif pool.liquidity_usd >= 100000:
            score += 10
        else:
            score += 5
            
        # 5. Activity score (0-15 points)
        if pool.transactions_24h >= 500:
            score += 15
            reasons.append("Very active")
        elif pool.transactions_24h >= 200:
            score += 10
        elif pool.transactions_24h >= 100:
            score += 5
            
        # 6. Buy pressure bonus (0-10 points)
        total = pool.buys_24h + pool.sells_24h
        if total > 0:
            buy_ratio = pool.buys_24h / total
            if buy_ratio >= 0.55:
                score += 10
                reasons.append("Buying > Selling")
                
        return max(0, min(100, score)), reasons
        
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics"""
        return {
            "pools_scanned": self.pools_scanned,
            "signals_generated": self.signals_generated,
            "chains_monitored": len(self.ALL_CHAINS),
            "pools_tracked": len(self.seen_pools)
        }
