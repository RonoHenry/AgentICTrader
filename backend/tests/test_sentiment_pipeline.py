"""
Unit tests for services/nlp/sentiment_pipeline.py

TDD: RED → GREEN → REFACTOR
Run: pytest backend/tests/test_sentiment_pipeline.py -v

All external dependencies (FinBERT model, HTTP calls, Kafka, Redis) are mocked.
Tests do NOT require network access or GPU.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import fakeredis.aioredis as fakeredis

from services.nlp.sentiment_pipeline import (
    SentimentPipeline,
    SentimentSignal,
    NewsArticle,
    SUPPORTED_INSTRUMENTS,
    TOPIC_SENTIMENT,
    TTL_SENTIMENT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_finbert_positive():
    """Mock FinBERT pipeline returning a positive label."""
    with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
        mock_clf = MagicMock()
        mock_clf.return_value = [{"label": "positive", "score": 0.9}]
        mock_pipeline_fn.return_value = mock_clf
        yield mock_clf


@pytest.fixture
def mock_finbert_negative():
    """Mock FinBERT pipeline returning a negative label."""
    with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
        mock_clf = MagicMock()
        mock_clf.return_value = [{"label": "negative", "score": 0.8}]
        mock_pipeline_fn.return_value = mock_clf
        yield mock_clf


@pytest.fixture
def mock_finbert_neutral():
    """Mock FinBERT pipeline returning a neutral label."""
    with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
        mock_clf = MagicMock()
        mock_clf.return_value = [{"label": "neutral", "score": 0.95}]
        mock_pipeline_fn.return_value = mock_clf
        yield mock_clf


@pytest.fixture
def mock_kafka():
    """Mock AIOKafkaProducer."""
    with patch("services.nlp.sentiment_pipeline.AIOKafkaProducer") as mock_cls:
        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()
        mock_producer.flush = AsyncMock()
        mock_producer.send = AsyncMock()
        mock_cls.return_value = mock_producer
        yield mock_producer


@pytest.fixture
def fake_redis():
    """In-process fakeredis instance (no real Redis required)."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_alpha_vantage_response():
    """Mock aiohttp response for Alpha Vantage with one recent article."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={
            "feed": [
                {
                    "title": "Fed raises rates",
                    "summary": "Federal Reserve raises interest rates by 25bps",
                    "time_published": "20260514T103000",
                    "source": "Reuters",
                    "url": "https://reuters.com/article/1",
                }
            ]
        }
    )
    return mock_resp


@pytest.fixture
def sample_articles():
    """A list of two recent NewsArticle objects."""
    now = datetime.now(tz=timezone.utc)
    return [
        NewsArticle(
            title="EUR rises on ECB decision",
            summary="The euro gained against the dollar after ECB raised rates.",
            published_at=now - timedelta(hours=1),
            source="alpha_vantage",
            url="https://example.com/1",
        ),
        NewsArticle(
            title="Eurozone inflation data",
            summary="Eurozone CPI came in above expectations.",
            published_at=now - timedelta(hours=2),
            source="alpha_vantage",
            url="https://example.com/2",
        ),
    ]


# ---------------------------------------------------------------------------
# Helper: build a connected pipeline with mocked Kafka + Redis
# ---------------------------------------------------------------------------

def _make_pipeline(fake_redis_instance=None, api_key="test_key") -> SentimentPipeline:
    """Return a SentimentPipeline with mocked internals (no real connections)."""
    sp = SentimentPipeline(
        kafka_bootstrap_servers="localhost:9092",
        redis_host="localhost",
        redis_port=6379,
        alpha_vantage_api_key=api_key,
    )
    return sp


# ===========================================================================
# 1. SentimentSignal dataclass
# ===========================================================================

class TestSentimentSignalDataclass:
    def test_sentiment_signal_has_required_fields(self):
        signal = SentimentSignal(
            instrument="EURUSD",
            score=0.75,
            direction="BULLISH",
            freshness_seconds=120,
            source="alpha_vantage",
        )
        assert signal.instrument == "EURUSD"
        assert signal.score == 0.75
        assert signal.direction == "BULLISH"
        assert signal.freshness_seconds == 120
        assert signal.source == "alpha_vantage"

    def test_sentiment_signal_score_range(self):
        signal = SentimentSignal(
            instrument="XAUUSD",
            score=-0.5,
            direction="BEARISH",
            freshness_seconds=60,
            source="reuters_rss",
        )
        assert isinstance(signal.score, float)
        assert signal.direction in ("BULLISH", "BEARISH", "NEUTRAL")


# ===========================================================================
# 2. NewsArticle dataclass
# ===========================================================================

class TestNewsArticleDataclass:
    def test_news_article_has_required_fields(self):
        now = datetime.now(tz=timezone.utc)
        article = NewsArticle(
            title="Gold hits record high",
            summary="Gold prices surged to an all-time high amid safe-haven demand.",
            published_at=now,
            source="reuters",
            url="https://reuters.com/gold",
        )
        assert article.title == "Gold hits record high"
        assert "Gold prices" in article.summary
        assert article.published_at == now
        assert article.source == "reuters"
        assert article.url == "https://reuters.com/gold"

    def test_news_article_url_defaults_to_empty_string(self):
        now = datetime.now(tz=timezone.utc)
        article = NewsArticle(
            title="Test",
            summary="Summary",
            published_at=now,
            source="test",
        )
        assert article.url == ""


# ===========================================================================
# 3. score_to_direction
# ===========================================================================

class TestScoreToDirection:
    def test_score_to_direction_bullish(self):
        assert SentimentPipeline.score_to_direction(0.5) == "BULLISH"

    def test_score_to_direction_bearish(self):
        assert SentimentPipeline.score_to_direction(-0.5) == "BEARISH"

    def test_score_to_direction_neutral_positive_boundary(self):
        assert SentimentPipeline.score_to_direction(0.05) == "NEUTRAL"

    def test_score_to_direction_neutral_negative_boundary(self):
        assert SentimentPipeline.score_to_direction(-0.05) == "NEUTRAL"

    def test_score_to_direction_exact_boundary_positive(self):
        # score == 0.1 is NOT > 0.1, so it should be NEUTRAL
        assert SentimentPipeline.score_to_direction(0.1) == "NEUTRAL"

    def test_score_to_direction_exact_boundary_negative(self):
        # score == -0.1 is NOT < -0.1, so it should be NEUTRAL
        assert SentimentPipeline.score_to_direction(-0.1) == "NEUTRAL"

    def test_score_to_direction_just_above_bullish_threshold(self):
        assert SentimentPipeline.score_to_direction(0.101) == "BULLISH"

    def test_score_to_direction_just_below_bearish_threshold(self):
        assert SentimentPipeline.score_to_direction(-0.101) == "BEARISH"

    def test_score_to_direction_zero(self):
        assert SentimentPipeline.score_to_direction(0.0) == "NEUTRAL"


# ===========================================================================
# 4. classify_sentiment (mock FinBERT)
# ===========================================================================

class TestClassifySentiment:
    def test_classify_sentiment_empty_articles_returns_zero(self):
        sp = _make_pipeline()
        result = sp.classify_sentiment([])
        assert result == 0.0

    def test_classify_sentiment_positive_articles(self, mock_finbert_positive, sample_articles):
        sp = _make_pipeline()
        result = sp.classify_sentiment(sample_articles)
        assert result > 0

    def test_classify_sentiment_negative_articles(self, mock_finbert_negative, sample_articles):
        sp = _make_pipeline()
        result = sp.classify_sentiment(sample_articles)
        assert result < 0

    def test_classify_sentiment_neutral_articles(self, mock_finbert_neutral, sample_articles):
        sp = _make_pipeline()
        result = sp.classify_sentiment(sample_articles)
        assert result == 0.0

    def test_classify_sentiment_mixed_articles(self, sample_articles):
        """Mix of positive and negative → mean score."""
        with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
            mock_clf = MagicMock()
            # First call positive (0.8), second call negative (0.6) → mean = (0.8 - 0.6) / 2 = 0.1
            mock_clf.side_effect = [
                [{"label": "positive", "score": 0.8}],
                [{"label": "negative", "score": 0.6}],
            ]
            mock_pipeline_fn.return_value = mock_clf

            sp = _make_pipeline()
            result = sp.classify_sentiment(sample_articles)
            # mean of [+0.8, -0.6] = 0.1
            assert abs(result - 0.1) < 1e-9

    def test_classify_sentiment_score_clamped_to_minus_one_plus_one(self):
        """Extreme confidence scores should be clamped to [-1.0, +1.0]."""
        with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
            mock_clf = MagicMock()
            # Return a score > 1.0 to test clamping (shouldn't happen in practice but be safe)
            mock_clf.return_value = [{"label": "positive", "score": 1.5}]
            mock_pipeline_fn.return_value = mock_clf

            now = datetime.now(tz=timezone.utc)
            articles = [
                NewsArticle("title", "summary", now, "test"),
            ]
            sp = _make_pipeline()
            result = sp.classify_sentiment(articles)
            assert result <= 1.0

    def test_classify_sentiment_single_article(self, mock_finbert_positive):
        now = datetime.now(tz=timezone.utc)
        articles = [NewsArticle("title", "summary", now, "test")]
        sp = _make_pipeline()
        result = sp.classify_sentiment(articles)
        assert result == pytest.approx(0.9)

    def test_classify_sentiment_loads_model_lazily(self):
        """FinBERT should not be loaded at __init__ time."""
        with patch("services.nlp.sentiment_pipeline.pipeline") as mock_pipeline_fn:
            sp = _make_pipeline()
            # Model should NOT have been loaded yet
            mock_pipeline_fn.assert_not_called()
            assert sp._classifier is None


# ===========================================================================
# 5. fetch_news (mock aiohttp)
# ===========================================================================

class TestFetchNews:
    async def test_fetch_news_alpha_vantage_returns_articles(
        self, mock_alpha_vantage_response
    ):
        sp = _make_pipeline(api_key="test_key")
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_alpha_vantage_response),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("services.nlp.sentiment_pipeline.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            articles = await sp.fetch_news("EURUSD")

        assert len(articles) == 1
        assert articles[0].title == "Fed raises rates"
        assert articles[0].source == "Reuters"

    async def test_fetch_news_filters_old_articles(self):
        """Articles older than 24 hours should be excluded."""
        old_time = datetime.now(tz=timezone.utc) - timedelta(hours=25)
        old_time_str = old_time.strftime("%Y%m%dT%H%M%S")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "feed": [
                    {
                        "title": "Old news",
                        "summary": "This is old",
                        "time_published": old_time_str,
                        "source": "Reuters",
                        "url": "",
                    }
                ]
            }
        )

        sp = _make_pipeline(api_key="test_key")
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("services.nlp.sentiment_pipeline.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            articles = await sp.fetch_news("EURUSD")

        assert articles == []

    async def test_fetch_news_http_error_returns_empty_list(self):
        """aiohttp raising an exception should return an empty list, not raise."""
        sp = _make_pipeline(api_key="test_key")

        with patch("services.nlp.sentiment_pipeline.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            articles = await sp.fetch_news("EURUSD")

        assert articles == []

    async def test_fetch_news_empty_feed_returns_empty_list(self):
        """An empty feed array should return an empty list."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"feed": []})

        sp = _make_pipeline(api_key="test_key")
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("services.nlp.sentiment_pipeline.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            articles = await sp.fetch_news("EURUSD")

        assert articles == []

    async def test_fetch_news_rss_fallback_when_no_api_key(self):
        """When api_key is empty, the Reuters RSS URL should be used."""
        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Gold surges on safe haven demand</title>
              <description>Gold prices rose sharply amid geopolitical tensions.</description>
              <pubDate>Thu, 14 May 2026 10:30:00 +0000</pubDate>
              <link>https://reuters.com/gold</link>
            </item>
          </channel>
        </rss>"""

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=rss_xml)

        sp = _make_pipeline(api_key="")  # no API key → RSS fallback
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))

        with patch("services.nlp.sentiment_pipeline.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)

            articles = await sp.fetch_news("XAUUSD")

        # Should have fetched from RSS (gold keyword matches XAUUSD)
        assert len(articles) >= 1
        assert articles[0].source == "reuters_rss"


# ===========================================================================
# 6. compute_signal
# ===========================================================================

class TestComputeSignal:
    async def test_compute_signal_returns_sentiment_signal(
        self, mock_finbert_positive
    ):
        sp = _make_pipeline()
        sp.fetch_news = AsyncMock(return_value=[])
        signal = await sp.compute_signal("EURUSD")
        assert isinstance(signal, SentimentSignal)
        assert signal.instrument == "EURUSD"

    async def test_compute_signal_score_in_valid_range(self, mock_finbert_positive, sample_articles):
        sp = _make_pipeline()
        sp.fetch_news = AsyncMock(return_value=sample_articles)
        signal = await sp.compute_signal("EURUSD")
        assert -1.0 <= signal.score <= 1.0

    async def test_compute_signal_direction_matches_score(self, mock_finbert_positive, sample_articles):
        sp = _make_pipeline()
        sp.fetch_news = AsyncMock(return_value=sample_articles)
        signal = await sp.compute_signal("EURUSD")
        expected_direction = SentimentPipeline.score_to_direction(signal.score)
        assert signal.direction == expected_direction

    async def test_compute_signal_freshness_seconds_is_non_negative(
        self, mock_finbert_positive, sample_articles
    ):
        sp = _make_pipeline()
        sp.fetch_news = AsyncMock(return_value=sample_articles)
        signal = await sp.compute_signal("EURUSD")
        assert signal.freshness_seconds >= 0

    async def test_compute_signal_no_articles_freshness_is_zero(self):
        sp = _make_pipeline()
        sp.fetch_news = AsyncMock(return_value=[])
        signal = await sp.compute_signal("EURUSD")
        assert signal.freshness_seconds == 0
        assert signal.score == 0.0


# ===========================================================================
# 7. publish_signal (mock Kafka)
# ===========================================================================

class TestPublishSignal:
    async def test_publish_signal_sends_to_correct_topic(self, mock_kafka):
        sp = _make_pipeline()
        sp._producer = mock_kafka

        signal = SentimentSignal(
            instrument="EURUSD",
            score=0.5,
            direction="BULLISH",
            freshness_seconds=60,
            source="alpha_vantage",
        )
        await sp.publish_signal(signal)

        mock_kafka.send.assert_called_once()
        call_args = mock_kafka.send.call_args
        assert call_args[0][0] == TOPIC_SENTIMENT

    async def test_publish_signal_key_is_instrument_bytes(self, mock_kafka):
        sp = _make_pipeline()
        sp._producer = mock_kafka

        signal = SentimentSignal(
            instrument="XAUUSD",
            score=-0.3,
            direction="BEARISH",
            freshness_seconds=300,
            source="reuters_rss",
        )
        await sp.publish_signal(signal)

        call_kwargs = mock_kafka.send.call_args[1]
        assert call_kwargs["key"] == b"XAUUSD"

    async def test_publish_signal_value_contains_required_fields(self, mock_kafka):
        sp = _make_pipeline()
        sp._producer = mock_kafka

        signal = SentimentSignal(
            instrument="BTCUSD",
            score=0.2,
            direction="BULLISH",
            freshness_seconds=120,
            source="alpha_vantage",
        )
        await sp.publish_signal(signal)

        call_kwargs = mock_kafka.send.call_args[1]
        payload = json.loads(call_kwargs["value"].decode("utf-8"))
        assert "instrument" in payload
        assert "score" in payload
        assert "direction" in payload
        assert "freshness_seconds" in payload
        assert "source" in payload

    async def test_publish_signal_score_is_float_in_message(self, mock_kafka):
        sp = _make_pipeline()
        sp._producer = mock_kafka

        signal = SentimentSignal(
            instrument="GBPUSD",
            score=0.65,
            direction="BULLISH",
            freshness_seconds=90,
            source="alpha_vantage",
        )
        await sp.publish_signal(signal)

        call_kwargs = mock_kafka.send.call_args[1]
        payload = json.loads(call_kwargs["value"].decode("utf-8"))
        assert isinstance(payload["score"], float)
        assert payload["score"] == 0.65


# ===========================================================================
# 8. cache_signal (mock Redis / fakeredis)
# ===========================================================================

class TestCacheSignal:
    async def test_cache_signal_stores_in_redis(self, fake_redis):
        sp = _make_pipeline()
        sp._redis = fake_redis

        signal = SentimentSignal(
            instrument="EURUSD",
            score=0.4,
            direction="BULLISH",
            freshness_seconds=200,
            source="alpha_vantage",
        )
        await sp.cache_signal(signal)

        raw = await fake_redis.get("sentiment:EURUSD")
        assert raw is not None

    async def test_cache_signal_ttl_is_900s(self, fake_redis):
        sp = _make_pipeline()
        sp._redis = fake_redis

        signal = SentimentSignal(
            instrument="XAUUSD",
            score=-0.2,
            direction="BEARISH",
            freshness_seconds=100,
            source="reuters_rss",
        )
        await sp.cache_signal(signal)

        ttl = await fake_redis.ttl("sentiment:XAUUSD")
        assert TTL_SENTIMENT - 2 <= ttl <= TTL_SENTIMENT

    async def test_cache_signal_value_contains_score_direction_freshness_source(
        self, fake_redis
    ):
        sp = _make_pipeline()
        sp._redis = fake_redis

        signal = SentimentSignal(
            instrument="US500",
            score=0.1,
            direction="NEUTRAL",
            freshness_seconds=500,
            source="alpha_vantage",
        )
        await sp.cache_signal(signal)

        raw = await fake_redis.get("sentiment:US500")
        data = json.loads(raw)
        assert "score" in data
        assert "direction" in data
        assert "freshness_seconds" in data
        assert "source" in data
        assert data["score"] == 0.1
        assert data["direction"] == "NEUTRAL"
        assert data["freshness_seconds"] == 500
        assert data["source"] == "alpha_vantage"


# ===========================================================================
# 9. run_once integration
# ===========================================================================

class TestRunOnce:
    async def test_run_once_calls_compute_cache_publish(self, mock_kafka, fake_redis):
        sp = _make_pipeline()
        sp._producer = mock_kafka
        sp._redis = fake_redis

        expected_signal = SentimentSignal(
            instrument="EURUSD",
            score=0.5,
            direction="BULLISH",
            freshness_seconds=60,
            source="alpha_vantage",
        )
        sp.compute_signal = AsyncMock(return_value=expected_signal)
        sp.cache_signal = AsyncMock()
        sp.publish_signal = AsyncMock()

        result = await sp.run_once("EURUSD")

        sp.compute_signal.assert_called_once_with("EURUSD")
        sp.cache_signal.assert_called_once_with(expected_signal)
        sp.publish_signal.assert_called_once_with(expected_signal)

    async def test_run_once_returns_sentiment_signal(self, mock_kafka, fake_redis):
        sp = _make_pipeline()
        sp._producer = mock_kafka
        sp._redis = fake_redis

        expected_signal = SentimentSignal(
            instrument="GBPUSD",
            score=-0.3,
            direction="BEARISH",
            freshness_seconds=120,
            source="reuters_rss",
        )
        sp.compute_signal = AsyncMock(return_value=expected_signal)
        sp.cache_signal = AsyncMock()
        sp.publish_signal = AsyncMock()

        result = await sp.run_once("GBPUSD")

        assert isinstance(result, SentimentSignal)
        assert result.instrument == "GBPUSD"
        assert result.score == -0.3


# ===========================================================================
# 10. run_all
# ===========================================================================

class TestRunAll:
    async def test_run_all_returns_signal_for_each_instrument(
        self, mock_kafka, fake_redis
    ):
        sp = _make_pipeline()
        sp._producer = mock_kafka
        sp._redis = fake_redis

        async def _mock_run_once(instrument: str) -> SentimentSignal:
            return SentimentSignal(
                instrument=instrument,
                score=0.0,
                direction="NEUTRAL",
                freshness_seconds=0,
                source="mock",
            )

        sp.run_once = _mock_run_once

        signals = await sp.run_all()
        assert len(signals) == len(SUPPORTED_INSTRUMENTS)

    async def test_run_all_all_signals_are_sentiment_signal_instances(
        self, mock_kafka, fake_redis
    ):
        sp = _make_pipeline()
        sp._producer = mock_kafka
        sp._redis = fake_redis

        async def _mock_run_once(instrument: str) -> SentimentSignal:
            return SentimentSignal(
                instrument=instrument,
                score=0.1,
                direction="BULLISH",
                freshness_seconds=30,
                source="mock",
            )

        sp.run_once = _mock_run_once

        signals = await sp.run_all()
        for signal in signals:
            assert isinstance(signal, SentimentSignal)

    async def test_run_all_instruments_match_supported_list(
        self, mock_kafka, fake_redis
    ):
        sp = _make_pipeline()
        sp._producer = mock_kafka
        sp._redis = fake_redis

        async def _mock_run_once(instrument: str) -> SentimentSignal:
            return SentimentSignal(
                instrument=instrument,
                score=0.0,
                direction="NEUTRAL",
                freshness_seconds=0,
                source="mock",
            )

        sp.run_once = _mock_run_once

        signals = await sp.run_all()
        returned_instruments = [s.instrument for s in signals]
        for instrument in SUPPORTED_INSTRUMENTS:
            assert instrument in returned_instruments
