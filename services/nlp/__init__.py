"""
services/nlp — NLP and sentiment analysis package for AgentICTrader.

Provides:
- FinBERT-based sentiment classification for financial news
- LLM macro event summariser and trade reasoning generator (Claude / template fallback)
- Economic calendar blackout monitor
"""
from services.nlp.sentiment_pipeline import (
    SentimentPipeline,
    SentimentSignal,
    NewsArticle,
    SUPPORTED_INSTRUMENTS,
    INSTRUMENT_KEYWORDS,
    TOPIC_SENTIMENT,
    FINBERT_MODEL,
    TTL_SENTIMENT,
)
from services.nlp.llm_service import (
    LLMService,
    CLAUDE_MODEL,
)

__all__ = [
    # Sentiment pipeline
    "SentimentPipeline",
    "SentimentSignal",
    "NewsArticle",
    "SUPPORTED_INSTRUMENTS",
    "INSTRUMENT_KEYWORDS",
    "TOPIC_SENTIMENT",
    "FINBERT_MODEL",
    "TTL_SENTIMENT",
    # LLM service
    "LLMService",
    "CLAUDE_MODEL",
]
