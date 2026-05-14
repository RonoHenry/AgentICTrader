"""
Sentiment pipeline for AgentICTrader.

Fetches financial news from Alpha Vantage (or Reuters RSS fallback),
classifies sentiment using FinBERT, caches results in Redis, and
publishes signals to Kafka.

Topics:
  sentiment.signals — SentimentSignal messages (key=instrument)

Redis keys:
  sentiment:{instrument} — cached SentimentSignal (TTL 900s)
"""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer

try:
    from transformers import pipeline
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'transformers' package is required for the sentiment pipeline. "
        "Install it with: pip install transformers>=4.39.0"
    ) from exc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_INSTRUMENTS = [
    "EURUSD", "GBPUSD", "US500", "US30", "XAUUSD", "BTCUSD", "ETHUSD", "XAUUSD"
]

# Instrument → currency/keyword mapping for news filtering
INSTRUMENT_KEYWORDS: dict[str, list[str]] = {
    "EURUSD": ["EUR", "euro", "ECB", "eurozone"],
    "GBPUSD": ["GBP", "pound", "sterling", "BOE", "Bank of England"],
    "US500":  ["S&P 500", "SPX", "US stocks", "equities", "Fed", "Federal Reserve"],
    "US30":   ["Dow Jones", "DJIA", "US stocks", "equities", "Fed"],
    "XAUUSD": ["gold", "XAU", "precious metals", "safe haven"],
    "BTCUSD": ["bitcoin", "BTC", "crypto", "cryptocurrency"],
    "ETHUSD": ["ethereum", "ETH", "crypto", "cryptocurrency"],
}

TOPIC_SENTIMENT = "sentiment.signals"
FINBERT_MODEL = "ProsusAI/finbert"
TTL_SENTIMENT = 900  # 15 minutes

# Alpha Vantage news endpoint
_AV_URL = (
    "https://www.alphavantage.co/query"
    "?function=NEWS_SENTIMENT&tickers={ticker}&apikey={key}&limit=50"
)
# Reuters RSS fallback
_REUTERS_RSS_URL = "https://feeds.reuters.com/reuters/businessNews"

# Time format used by Alpha Vantage: "20240115T103000"
_AV_TIME_FORMAT = "%Y%m%dT%H%M%S"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SentimentSignal:
    """Sentiment signal for a single instrument."""
    instrument: str
    score: float          # -1.0 (bearish) to +1.0 (bullish)
    direction: str        # "BULLISH" | "BEARISH" | "NEUTRAL"
    freshness_seconds: int
    source: str           # "alpha_vantage" | "reuters_rss" | "mock"


@dataclass
class NewsArticle:
    """A single news article."""
    title: str
    summary: str
    published_at: datetime
    source: str
    url: str = ""


# ---------------------------------------------------------------------------
# SentimentPipeline
# ---------------------------------------------------------------------------

class SentimentPipeline:
    """
    End-to-end sentiment pipeline: fetch news → classify → cache → publish.

    Usage::

        pipeline = SentimentPipeline(alpha_vantage_api_key="YOUR_KEY")
        await pipeline.connect()
        signal = await pipeline.run_once("EURUSD")
        await pipeline.close()
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        alpha_vantage_api_key: str = "",
        finbert_model: str = FINBERT_MODEL,
    ) -> None:
        self._kafka_bootstrap_servers = kafka_bootstrap_servers
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._alpha_vantage_api_key = alpha_vantage_api_key
        self._finbert_model = finbert_model

        self._producer: Optional[AIOKafkaProducer] = None
        self._redis: Optional[aioredis.Redis] = None
        # FinBERT classifier — loaded lazily on first call to classify_sentiment
        self._classifier = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start Kafka producer and Redis connection."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._kafka_bootstrap_servers,
        )
        await self._producer.start()

        self._redis = aioredis.Redis(
            host=self._redis_host,
            port=self._redis_port,
            decode_responses=True,
        )
        logger.info(
            "SentimentPipeline connected (kafka=%s, redis=%s:%s)",
            self._kafka_bootstrap_servers,
            self._redis_host,
            self._redis_port,
        )

    async def close(self) -> None:
        """Flush Kafka, close Redis."""
        if self._producer is not None:
            try:
                await self._producer.flush()
                await self._producer.stop()
            except Exception:
                pass
            finally:
                self._producer = None

        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            finally:
                self._redis = None

        logger.info("SentimentPipeline closed")

    # ------------------------------------------------------------------
    # News fetching
    # ------------------------------------------------------------------

    async def fetch_news(self, instrument: str) -> list[NewsArticle]:
        """Fetch news articles for *instrument* from Alpha Vantage.

        Falls back to Reuters RSS if ``alpha_vantage_api_key`` is empty.
        Returns an empty list on HTTP error (never raises).
        """
        if self._alpha_vantage_api_key:
            return await self._fetch_alpha_vantage(instrument)
        return await self._fetch_reuters_rss(instrument)

    async def _fetch_alpha_vantage(self, instrument: str) -> list[NewsArticle]:
        """Fetch from Alpha Vantage NEWS_SENTIMENT endpoint."""
        # Map instrument to a ticker symbol Alpha Vantage understands
        ticker = instrument  # e.g. "EURUSD", "XAUUSD" — AV accepts forex tickers
        url = _AV_URL.format(ticker=ticker, key=self._alpha_vantage_api_key)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Alpha Vantage returned HTTP %s for %s", resp.status, instrument
                        )
                        return []
                    data = await resp.json()
        except Exception as exc:
            logger.warning("Alpha Vantage fetch failed for %s: %s", instrument, exc)
            return []

        articles: list[NewsArticle] = []
        for item in data.get("feed", []):
            try:
                published_at = datetime.strptime(
                    item["time_published"], _AV_TIME_FORMAT
                ).replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                continue

            if published_at < cutoff:
                continue  # older than 24 hours — skip

            articles.append(
                NewsArticle(
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    published_at=published_at,
                    source=item.get("source", "alpha_vantage"),
                    url=item.get("url", ""),
                )
            )

        logger.debug("Alpha Vantage returned %d articles for %s", len(articles), instrument)
        return articles

    async def _fetch_reuters_rss(self, instrument: str) -> list[NewsArticle]:
        """Fetch from Reuters RSS and filter by instrument keywords."""
        keywords = INSTRUMENT_KEYWORDS.get(instrument, [])
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_REUTERS_RSS_URL) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Reuters RSS returned HTTP %s for %s", resp.status, instrument
                        )
                        return []
                    text = await resp.text()
        except Exception as exc:
            logger.warning("Reuters RSS fetch failed for %s: %s", instrument, exc)
            return []

        articles: list[NewsArticle] = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            logger.warning("Reuters RSS parse error: %s", exc)
            return []

        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date_str = (item.findtext("pubDate") or "").strip()
            link = (item.findtext("link") or "").strip()

            # Filter by instrument keywords
            combined = f"{title} {description}"
            if keywords and not any(kw.lower() in combined.lower() for kw in keywords):
                continue

            # Parse pubDate (RFC 2822 format)
            published_at: datetime
            try:
                from email.utils import parsedate_to_datetime
                published_at = parsedate_to_datetime(pub_date_str)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
            except Exception:
                published_at = datetime.now(tz=timezone.utc)

            if published_at < cutoff:
                continue

            articles.append(
                NewsArticle(
                    title=title,
                    summary=description,
                    published_at=published_at,
                    source="reuters_rss",
                    url=link,
                )
            )

        logger.debug("Reuters RSS returned %d articles for %s", len(articles), instrument)
        return articles

    # ------------------------------------------------------------------
    # Sentiment classification
    # ------------------------------------------------------------------

    def classify_sentiment(self, articles: list[NewsArticle]) -> float:
        """Run FinBERT on each article's title + summary.

        Returns mean score in [-1.0, +1.0]:
          - FinBERT 'positive' label → +score
          - FinBERT 'negative' label → -score
          - FinBERT 'neutral'  label → 0.0

        Returns 0.0 if *articles* is empty.
        """
        if not articles:
            return 0.0

        # Lazy-load FinBERT on first call
        if self._classifier is None:
            self._classifier = pipeline(
                "text-classification",
                model=self._finbert_model,
            )

        scores: list[float] = []
        for article in articles:
            text = f"{article.title}. {article.summary}"[:512]
            try:
                result = self._classifier(text)
                label = result[0]["label"].lower()
                confidence = float(result[0]["score"])
                if label == "positive":
                    scores.append(confidence)
                elif label == "negative":
                    scores.append(-confidence)
                else:  # neutral
                    scores.append(0.0)
            except Exception as exc:
                logger.warning("FinBERT classification failed: %s", exc)
                scores.append(0.0)

        if not scores:
            return 0.0

        mean_score = sum(scores) / len(scores)
        # Clamp to [-1.0, +1.0]
        return max(-1.0, min(1.0, mean_score))

    # ------------------------------------------------------------------
    # Direction mapping
    # ------------------------------------------------------------------

    @staticmethod
    def score_to_direction(score: float) -> str:
        """Map a numeric score to a direction string.

        score > 0.1  → 'BULLISH'
        score < -0.1 → 'BEARISH'
        else         → 'NEUTRAL'
        """
        if score > 0.1:
            return "BULLISH"
        if score < -0.1:
            return "BEARISH"
        return "NEUTRAL"

    # ------------------------------------------------------------------
    # Signal computation
    # ------------------------------------------------------------------

    async def compute_signal(self, instrument: str) -> SentimentSignal:
        """Fetch news, classify, return a SentimentSignal."""
        articles = await self.fetch_news(instrument)
        score = self.classify_sentiment(articles)
        direction = self.score_to_direction(score)

        # freshness_seconds = seconds since the most recent article's published_at
        if articles:
            most_recent = max(a.published_at for a in articles)
            now = datetime.now(tz=timezone.utc)
            freshness_seconds = max(0, int((now - most_recent).total_seconds()))
            source = articles[0].source
        else:
            freshness_seconds = 0
            source = "alpha_vantage" if self._alpha_vantage_api_key else "reuters_rss"

        return SentimentSignal(
            instrument=instrument,
            score=score,
            direction=direction,
            freshness_seconds=freshness_seconds,
            source=source,
        )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_signal(self, signal: SentimentSignal) -> None:
        """Publish *signal* to Kafka topic ``sentiment.signals``.

        Message key  = instrument (bytes).
        Message value = JSON: {instrument, score, direction, freshness_seconds, source}
        """
        key = signal.instrument.encode("utf-8")
        value = json.dumps(
            {
                "instrument": signal.instrument,
                "score": signal.score,
                "direction": signal.direction,
                "freshness_seconds": signal.freshness_seconds,
                "source": signal.source,
            }
        ).encode("utf-8")
        await self._producer.send(TOPIC_SENTIMENT, key=key, value=value)
        logger.debug("Published sentiment signal for %s to %s", signal.instrument, TOPIC_SENTIMENT)

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    async def cache_signal(self, signal: SentimentSignal) -> None:
        """Cache *signal* in Redis.

        Key  = ``sentiment:{instrument}``
        TTL  = 900 seconds
        Value = JSON dict: {score, direction, freshness_seconds, source}
        """
        key = f"sentiment:{signal.instrument}"
        value = json.dumps(
            {
                "score": signal.score,
                "direction": signal.direction,
                "freshness_seconds": signal.freshness_seconds,
                "source": signal.source,
            }
        )
        await self._redis.set(key, value, ex=TTL_SENTIMENT)
        logger.debug("Cached sentiment signal for %s (TTL=%ss)", signal.instrument, TTL_SENTIMENT)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def run_once(self, instrument: str) -> SentimentSignal:
        """compute_signal → cache_signal → publish_signal → return signal."""
        signal = await self.compute_signal(instrument)
        await self.cache_signal(signal)
        await self.publish_signal(signal)
        return signal

    async def run_all(self) -> list[SentimentSignal]:
        """run_once for all SUPPORTED_INSTRUMENTS, return list of signals."""
        signals: list[SentimentSignal] = []
        for instrument in SUPPORTED_INSTRUMENTS:
            signal = await self.run_once(instrument)
            signals.append(signal)
        return signals
