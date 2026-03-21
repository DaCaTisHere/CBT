"""
OpenAI Analyzer - LLM-powered token analysis for trading decisions.

Uses GPT to analyze the combination of technical, security, and market data
to provide an intelligent trading recommendation that goes beyond rule-based scoring.
"""

import json
from typing import Dict, Any, Optional, Tuple

from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_client = None
_available = False


def _get_client():
    """Lazy-init OpenAI client."""
    global _client, _available
    if _client is not None:
        return _client
    
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.info("[AI] OpenAI API key not configured, LLM analysis disabled")
        _available = False
        return None
    
    try:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=api_key)
        _available = True
        logger.info("[AI] OpenAI LLM analyzer initialized")
        return _client
    except Exception as e:
        logger.warning(f"[AI] OpenAI init failed: {e}")
        _available = False
        return None


async def analyze_token_with_llm(
    token_symbol: str,
    chain: str,
    current_price: float,
    liquidity_usd: float,
    volume_24h: float,
    security_score: float,
    sentiment_score: float,
    entry_score: float,
    honeypot_result: Optional[Dict] = None,
    rugpull_result: Optional[Dict] = None,
    reasoning: list = None,
    warnings: list = None,
) -> Tuple[float, str, list]:
    """
    Analyze a token using OpenAI GPT for intelligent decision-making.
    
    Returns:
        (confidence_adjustment, summary, ai_reasons)
        - confidence_adjustment: float between -0.3 and +0.3 to add to base confidence
        - summary: one-line LLM verdict
        - ai_reasons: list of reasoning strings from the LLM
    """
    client = _get_client()
    if not client:
        return 0.0, "", []

    try:
        context = {
            "token": token_symbol,
            "chain": chain,
            "price_usd": current_price,
            "liquidity_usd": liquidity_usd,
            "volume_24h_usd": volume_24h,
            "security_score": security_score,
            "sentiment_score": sentiment_score,
            "entry_timing_score": entry_score,
            "existing_reasoning": (reasoning or [])[:5],
            "existing_warnings": (warnings or [])[:5],
        }

        if honeypot_result:
            context["honeypot"] = {
                "is_safe": honeypot_result.get("is_safe"),
                "risk_level": honeypot_result.get("risk_level"),
                "buy_tax": honeypot_result.get("details", {}).get("buy_tax"),
                "sell_tax": honeypot_result.get("details", {}).get("sell_tax"),
            }

        if rugpull_result:
            context["rugpull"] = {
                "risk_score": rugpull_result.get("risk_score", rugpull_result[0] if isinstance(rugpull_result, tuple) else 0),
                "risk_factors": rugpull_result.get("risk_factors", [])[:3] if isinstance(rugpull_result, dict) else [],
            }

        prompt = f"""You are a crypto trading AI analyst. Analyze this token and provide a trading recommendation.

TOKEN DATA:
{json.dumps(context, indent=2, default=str)}

Respond in JSON only:
{{
  "confidence_adjustment": <float between -0.3 and 0.3>,
  "verdict": "<one-line verdict: BUY / WAIT / SKIP and why>",
  "reasons": ["<reason 1>", "<reason 2>", "<reason 3>"],
  "risk_flags": ["<risk if any>"],
  "market_insight": "<brief market context>"
}}

Rules:
- Positive adjustment = more likely to buy, negative = less likely
- Be conservative: high security_score (>60) should push negative
- Low liquidity (<$10k) is a red flag
- Consider the combination of ALL factors, not just individual scores
- If data is insufficient, lean toward SKIP with negative adjustment"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a crypto trading risk analyst. Always respond in valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        adjustment = max(-0.3, min(0.3, float(result.get("confidence_adjustment", 0))))
        verdict = result.get("verdict", "")
        reasons = result.get("reasons", [])
        risks = result.get("risk_flags", [])
        insight = result.get("market_insight", "")

        ai_reasons = []
        if verdict:
            ai_reasons.append(f"LLM: {verdict}")
        for r in reasons[:3]:
            ai_reasons.append(f"LLM: {r}")
        if insight:
            ai_reasons.append(f"LLM insight: {insight}")
        for risk in risks[:2]:
            ai_reasons.append(f"LLM risk: {risk}")

        logger.info(f"[AI] LLM verdict for {token_symbol}: {verdict} (adj: {adjustment:+.2f})")
        return adjustment, verdict, ai_reasons

    except json.JSONDecodeError:
        logger.warning(f"[AI] LLM returned invalid JSON for {token_symbol}")
        return 0.0, "", []
    except Exception as e:
        logger.warning(f"[AI] LLM analysis failed for {token_symbol}: {e}")
        return 0.0, "", []


async def analyze_portfolio_performance(
    total_trades: int,
    win_rate: float,
    total_pnl_usd: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    active_strategies: list,
) -> Optional[str]:
    """
    Ask GPT to analyze portfolio performance and suggest improvements.
    Called periodically (every 6h) for self-improvement insights.
    """
    client = _get_client()
    if not client:
        return None

    try:
        prompt = f"""Analyze this crypto trading bot's performance and suggest concrete improvements:

PERFORMANCE:
- Total trades: {total_trades}
- Win rate: {win_rate:.1f}%
- Total PnL: ${total_pnl_usd:.2f}
- Average win: +{avg_win_pct:.2f}%
- Average loss: {avg_loss_pct:.2f}%
- Active strategies: {', '.join(active_strategies)}

Provide 3-5 specific, actionable suggestions to improve profitability.
Be concise (max 200 words total). Focus on risk management and entry timing."""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a quantitative trading advisor. Be specific and actionable."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.5,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"[AI] Portfolio analysis failed: {e}")
        return None
