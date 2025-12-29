"""
NLP Engine for Sentiment Analysis

Uses:
- Pre-trained models (DistilBERT fine-tuned for financial sentiment)
- Keyword-based sentiment scoring
- Emoji sentiment analysis
- Crypto-specific lexicon
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

from src.utils.logger import get_logger


logger = get_logger(__name__)


class NLPEngine:
    """
    Natural Language Processing engine for sentiment analysis
    """
    
    # Crypto-specific sentiment lexicon
    POSITIVE_KEYWORDS = [
        "bullish", "moon", "pump", "rally", "surge", "breakout",
        "ath", "all time high", "mooning", "rocket", "lambo",
        "buy", "long", "accumulate", "hodl", "hold",
        "bullrun", "uptrend", "support", "bounce", "recovery",
        "adoption", "partnership", "integration", "listing"
    ]
    
    NEGATIVE_KEYWORDS = [
        "bearish", "dump", "crash", "dump", "drop", "fall",
        "fud", "scam", "rug", "rugpull", "hack", "exploit",
        "sell", "short", "exit", "panic", "fear",
        "bearmarket", "downtrend", "resistance", "rejection",
        "delisting", "ban", "regulation", "lawsuit"
    ]
    
    # Emoji sentiment
    POSITIVE_EMOJIS = [
        "🚀", "🌙", "💎", "🙌", "💪", "🔥", "📈", "🐂", "✅", "💚", "🟢"
    ]
    
    NEGATIVE_EMOJIS = [
        "📉", "🐻", "❌", "⚠️", "🔴", "💔", "😰", "😱", "🚨"
    ]
    
    def __init__(self):
        self.logger = logger
        self.model = None
        self.tokenizer = None
        self.is_initialized = False
        
        # Stats
        self.texts_analyzed = 0
        
        self.logger.info("[NLP] Engine initialized (keyword-based mode)")
    
    async def initialize(self):
        """Initialize NLP models (optional)"""
        try:
            # Try to load pre-trained model
            await self._load_transformer_model()
            self.is_initialized = True
        except Exception as e:
            self.logger.warning(f"[NLP] Could not load transformer model: {e}")
            self.logger.info("[NLP] Using keyword-based sentiment analysis")
            self.is_initialized = True
    
    async def _load_transformer_model(self):
        """
        Load pre-trained transformer model for sentiment analysis
        
        Options:
        - distilbert-base-uncased-finetuned-sst-2-english
        - finiteautomata/bertweet-base-sentiment-analysis
        - cardiffnlp/twitter-roberta-base-sentiment
        """
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            
            self.logger.info("[NLP] Loading transformer model...")
            
            model_name = "cardiffnlp/twitter-roberta-base-sentiment"
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            self.logger.info(f"[NLP] Model loaded: {model_name}")
            
        except ImportError:
            self.logger.warning("[NLP] Transformers library not available")
            raise
        except Exception as e:
            self.logger.error(f"[NLP] Model loading failed: {e}")
            raise
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text
        
        Args:
            text: Text to analyze
        
        Returns:
            Dict with sentiment, score, confidence
        """
        self.texts_analyzed += 1
        
        # Clean text
        text_clean = self._clean_text(text)
        
        # Try transformer model first
        if self.model and self.tokenizer:
            try:
                result = await self._analyze_with_transformer(text_clean)
                return result
            except Exception as e:
                self.logger.error(f"[NLP] Transformer analysis failed: {e}")
        
        # Fallback to keyword-based
        result = await self._analyze_with_keywords(text_clean, text)  # Pass original for emojis
        
        return result
    
    def _clean_text(self, text: str) -> str:
        """Clean and preprocess text"""
        # Remove URLs
        text = re.sub(r'http\S+|www\S+', '', text)
        
        # Remove mentions
        text = re.sub(r'@\w+', '', text)
        
        # Remove hashtags (keep the word)
        text = re.sub(r'#(\w+)', r'\1', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text.lower()
    
    async def _analyze_with_transformer(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment using transformer model
        """
        import torch
        
        # Tokenize
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        
        # Get predictions
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Extract sentiment
        scores = predictions[0].tolist()
        
        # Map to sentiment labels (model-dependent)
        # For twitter-roberta-base-sentiment: [negative, neutral, positive]
        sentiment_map = {
            0: "negative",
            1: "neutral",
            2: "positive"
        }
        
        predicted_class = torch.argmax(predictions).item()
        sentiment = sentiment_map[predicted_class]
        confidence = scores[predicted_class]
        
        return {
            "sentiment": sentiment,
            "score": scores[predicted_class] - scores[0],  # Positive - Negative
            "confidence": confidence,
            "scores": {
                "negative": scores[0],
                "neutral": scores[1] if len(scores) > 1 else 0,
                "positive": scores[2] if len(scores) > 2 else scores[1]
            },
            "method": "transformer"
        }
    
    async def _analyze_with_keywords(self, text_clean: str, text_original: str) -> Dict[str, Any]:
        """
        Analyze sentiment using keyword matching and emoji analysis
        """
        score = 0.0
        positive_count = 0
        negative_count = 0
        
        # Check positive keywords
        for keyword in self.POSITIVE_KEYWORDS:
            if keyword in text_clean:
                positive_count += 1
                score += 0.1
        
        # Check negative keywords
        for keyword in self.NEGATIVE_KEYWORDS:
            if keyword in text_clean:
                negative_count += 1
                score -= 0.1
        
        # Check emojis in original text
        for emoji in self.POSITIVE_EMOJIS:
            count = text_original.count(emoji)
            if count > 0:
                positive_count += count
                score += 0.05 * count
        
        for emoji in self.NEGATIVE_EMOJIS:
            count = text_original.count(emoji)
            if count > 0:
                negative_count += count
                score -= 0.05 * count
        
        # Normalize score to [-1, 1]
        score = max(-1.0, min(1.0, score))
        
        # Determine sentiment
        if score > 0.15:
            sentiment = "positive"
        elif score < -0.15:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        # Calculate confidence
        total_signals = positive_count + negative_count
        confidence = min(0.9, total_signals * 0.1) if total_signals > 0 else 0.3
        
        return {
            "sentiment": sentiment,
            "score": score,
            "confidence": confidence,
            "signals": {
                "positive": positive_count,
                "negative": negative_count,
                "total": total_signals
            },
            "method": "keyword"
        }
    
    async def analyze_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze multiple texts in batch
        
        Args:
            texts: List of texts to analyze
        
        Returns:
            List of sentiment results
        """
        results = []
        
        for text in texts:
            result = await self.analyze_sentiment(text)
            results.append(result)
        
        return results
    
    def extract_tokens_mentioned(self, text: str) -> List[str]:
        """
        Extract crypto token symbols mentioned in text
        
        Returns:
            List of token symbols (e.g., ["BTC", "ETH"])
        """
        tokens = []
        
        # Pattern 1: $SYMBOL
        cashtags = re.findall(r'\$([A-Z]{2,10})\b', text)
        tokens.extend(cashtags)
        
        # Pattern 2: Common names
        common_tokens = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "btc": "BTC",
            "eth": "ETH",
            "bnb": "BNB",
            "solana": "SOL",
            "cardano": "ADA",
            "ripple": "XRP",
            "polkadot": "DOT",
            "dogecoin": "DOGE",
            "shiba": "SHIB"
        }
        
        text_lower = text.lower()
        for name, symbol in common_tokens.items():
            if name in text_lower and symbol not in tokens:
                tokens.append(symbol)
        
        # Remove duplicates
        return list(set(tokens))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get NLP engine statistics"""
        return {
            "texts_analyzed": self.texts_analyzed,
            "model_loaded": self.model is not None,
            "method": "transformer" if self.model else "keyword"
        }


class SentimentAggregator:
    """
    Aggregates sentiment scores across multiple posts/time periods
    """
    
    def __init__(self, window_minutes: int = 60):
        """
        Initialize aggregator
        
        Args:
            window_minutes: Time window for aggregation
        """
        self.window_minutes = window_minutes
        self.sentiment_history: List[Dict[str, Any]] = []
        self.logger = logger
    
    def add_sentiment(self, sentiment_data: Dict[str, Any]):
        """Add a sentiment data point"""
        sentiment_data["timestamp"] = datetime.utcnow()
        self.sentiment_history.append(sentiment_data)
        
        # Clean old data
        self._clean_old_data()
    
    def _clean_old_data(self):
        """Remove data older than window"""
        cutoff = datetime.utcnow().timestamp() - (self.window_minutes * 60)
        
        self.sentiment_history = [
            item for item in self.sentiment_history
            if item["timestamp"].timestamp() > cutoff
        ]
    
    def get_aggregated_sentiment(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Get aggregated sentiment for a token or overall
        
        Args:
            token: Optional token symbol (e.g., "BTC")
        
        Returns:
            Aggregated sentiment data
        """
        # Filter by token if specified
        if token:
            data = [
                item for item in self.sentiment_history
                if token in item.get("tokens", [])
            ]
        else:
            data = self.sentiment_history
        
        if not data:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "volume": 0,
                "window_minutes": self.window_minutes
            }
        
        # Calculate aggregates
        total_score = sum(item["score"] for item in data)
        avg_score = total_score / len(data)
        
        # Count sentiments
        sentiment_counts = {
            "positive": sum(1 for item in data if item["sentiment"] == "positive"),
            "neutral": sum(1 for item in data if item["sentiment"] == "neutral"),
            "negative": sum(1 for item in data if item["sentiment"] == "negative")
        }
        
        # Determine overall sentiment
        if sentiment_counts["positive"] > sentiment_counts["negative"]:
            overall_sentiment = "positive"
        elif sentiment_counts["negative"] > sentiment_counts["positive"]:
            overall_sentiment = "negative"
        else:
            overall_sentiment = "neutral"
        
        # Calculate confidence based on volume and consistency
        volume = len(data)
        consistency = max(sentiment_counts.values()) / volume if volume > 0 else 0
        confidence = min(0.95, (volume / 100) * consistency)
        
        return {
            "sentiment": overall_sentiment,
            "score": avg_score,
            "confidence": confidence,
            "volume": volume,
            "counts": sentiment_counts,
            "window_minutes": self.window_minutes,
            "token": token
        }

