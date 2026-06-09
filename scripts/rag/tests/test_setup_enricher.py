"""Tests for HTF structure extraction, PD array detection, and time window
classification in the setup enricher."""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from scripts.rag.utils.setup_enricher import SetupEnricher, EnrichedSetup
from hypothesis import given, strategies as st, assume


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_candle(open_, high, low, close, time="2024-01-15T09:00:00Z"):
    return {
        "time": time,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


def make_trade(entry_price=1.5000, direction="BUY", instrument="EURUSD"):
    return {
        "trade_id": "TRD-001",
        "instrument": instrument,
        "direction": direction,
        "entry": {"time": "2024-01-15T09:15:00Z", "price": entry_price},
        "exit": {"time": "2024-01-15T11:00:00Z", "price": entry_price + 0.005},
        "risk": {
            "stop_loss": entry_price - 0.002,
            "take_profit": entry_price + 0.006,
            "position_size": 1.0,
        },
        "outcome": {"r_multiple": 2.5, "pnl_usd": 250.0},
    }


# ---------------------------------------------------------------------------
# Task 3.2 – HTF Structure Extraction
# ---------------------------------------------------------------------------


class TestHTFStructureExtraction:
    def test_enrich_returns_enriched_setup(self):
        """Enriched setup is returned with HTF fields populated."""
        enricher = SetupEnricher(htf_timeframe="H1")
        trade = make_trade(entry_price=1.5050)
        candles = [make_candle(1.5000, 1.5100, 1.4950, 1.5050)]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5100)]

        result = enricher.enrich(trade, candles, htf_candles)

        assert isinstance(result, EnrichedSetup)
        assert result.trade_id == "TRD-001"
        assert result.htf_open == 1.5000
        assert result.htf_high == 1.5200
        assert result.htf_low == 1.4900
        assert result.htf_open_bias == "BULLISH"  # price 1.5050 > open 1.5000

    def test_htf_open_bias_bearish_when_price_below_open(self):
        """HTF bias is BEARISH when entry price is below HTF open."""
        enricher = SetupEnricher()
        trade = make_trade(entry_price=1.4950)
        candles = [make_candle(1.5000, 1.5100, 1.4900, 1.4950)]
        htf_candles = [make_candle(1.5000, 1.5100, 1.4900, 1.4950)]

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.htf_open_bias == "BEARISH"

    def test_htf_proximity_percentages_sum_to_100_when_price_in_range(self):
        """HTF proximity percentages sum to 100 when price is within HTF range."""
        enricher = SetupEnricher()
        entry_price = 1.5050  # in range [1.4900, 1.5200]
        trade = make_trade(entry_price=entry_price)
        candles = [make_candle(1.5000, 1.5100, 1.4950, entry_price)]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, entry_price)]

        result = enricher.enrich(trade, candles, htf_candles)
        total = result.htf_high_proximity_pct + result.htf_low_proximity_pct
        assert abs(total - 100.0) < 0.01

    def test_caching_returns_same_result_for_same_inputs(self):
        """Caching: calling enrich twice with same inputs returns same HTF result."""
        enricher = SetupEnricher()
        trade = make_trade()
        candles = [make_candle(1.5000, 1.5100, 1.4950, 1.5050)]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5050)]

        result1 = enricher.enrich(trade, candles, htf_candles)
        result2 = enricher.enrich(trade, candles, htf_candles)

        assert result1.htf_open == result2.htf_open
        assert result1.htf_open_bias == result2.htf_open_bias


# ---------------------------------------------------------------------------
# Task 3.3 – PD Array Detection
# ---------------------------------------------------------------------------


class TestPDArrayDetection:
    def test_fvg_detected_in_enriched_setup(self):
        """FVG is detected when gap exists between candle highs/lows."""
        enricher = SetupEnricher()
        trade = make_trade(entry_price=1.5070)
        # Create candles that form a bullish FVG: candle[-3].high < candle[-1].low
        candles = [
            make_candle(1.5000, 1.5020, 1.4980, 1.5010),  # candle i-2: high=1.5020
            make_candle(1.5010, 1.5030, 1.4990, 1.5025),  # candle i-1
            make_candle(1.5030, 1.5100, 1.5025, 1.5070),  # candle i: low=1.5025 > high[i-2]=1.5020
        ]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5070)]

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.fvg_present is True

    def test_bos_detected_when_close_breaks_swing_high(self):
        """BOS is detected when price closes above a prior swing high."""
        enricher = SetupEnricher()
        trade = make_trade(entry_price=1.5150)
        candles = [
            make_candle(1.5000, 1.5080, 1.4980, 1.5060),  # swing high at 1.5080
            make_candle(1.5060, 1.5070, 1.5020, 1.5030),  # lower high
            make_candle(1.5030, 1.5160, 1.5010, 1.5150),  # close > swing high → BOS
        ]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5150)]

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.bos_detected is True

    def test_pd_array_fields_present_in_enriched_setup(self):
        """All PD array fields are present in enriched setup."""
        enricher = SetupEnricher()
        trade = make_trade()
        candles = [make_candle(1.5000, 1.5100, 1.4950, 1.5050)]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5050)]

        result = enricher.enrich(trade, candles, htf_candles)

        assert hasattr(result, "bos_detected")
        assert hasattr(result, "choch_detected")
        assert hasattr(result, "fvg_present")
        assert hasattr(result, "liquidity_sweep")
        assert hasattr(result, "swing_high_distance")
        assert hasattr(result, "swing_low_distance")
        assert hasattr(result, "htf_trend_bias")
        assert isinstance(result.bos_detected, bool)


# ---------------------------------------------------------------------------
# Task 3.4 – Time Window Classification
# ---------------------------------------------------------------------------


class TestTimeWindowClassification:
    def test_london_killzone_classification(self):
        """Entry time in London killzone hours is classified correctly."""
        enricher = SetupEnricher()
        # 09:00 UTC = 04:00 NY in winter (EST, UTC-5) → LONDON_KILLZONE
        trade = {
            "trade_id": "TRD-LDN",
            "instrument": "EURUSD",
            "direction": "BUY",
            "entry": {"time": "2024-01-15T09:00:00Z", "price": 1.5050},
            "exit": {"time": "2024-01-15T11:00:00Z", "price": 1.5100},
            "risk": {
                "stop_loss": 1.5000,
                "take_profit": 1.5150,
                "position_size": 1.0,
            },
            "outcome": {"r_multiple": 2.5, "pnl_usd": 250.0},
        }
        candles = [
            make_candle(1.5000, 1.5100, 1.4950, 1.5050, time="2024-01-15T09:00:00Z")
        ]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5050)]

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.time_window in {"LONDON_KILLZONE", "LONDON_SILVER_BULLET"}

    def test_ny_am_killzone_classification(self):
        """Entry time in NY AM killzone hours is classified correctly."""
        enricher = SetupEnricher()
        # 14:00 UTC = 09:00 NY in winter (EST) → NY_AM_KILLZONE
        trade = {
            "trade_id": "TRD-NY",
            "instrument": "EURUSD",
            "direction": "BUY",
            "entry": {"time": "2024-01-15T14:00:00Z", "price": 1.5050},
            "exit": {"time": "2024-01-15T15:00:00Z", "price": 1.5100},
            "risk": {
                "stop_loss": 1.5000,
                "take_profit": 1.5150,
                "position_size": 1.0,
            },
            "outcome": {"r_multiple": 2.5, "pnl_usd": 250.0},
        }
        candles = [
            make_candle(1.5000, 1.5100, 1.4950, 1.5050, time="2024-01-15T14:00:00Z")
        ]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5050)]

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.time_window in {"NY_AM_KILLZONE", "NEWS_WINDOW"}

    def test_is_killzone_true_for_killzone_windows(self):
        """is_killzone is True for killzone time windows."""
        enricher = SetupEnricher()
        # 14:00 UTC = NY AM killzone
        trade = {
            "trade_id": "TRD-KZ",
            "instrument": "EURUSD",
            "direction": "BUY",
            "entry": {"time": "2024-01-15T14:00:00Z", "price": 1.5050},
            "exit": {"time": "2024-01-15T15:00:00Z", "price": 1.5100},
            "risk": {
                "stop_loss": 1.5000,
                "take_profit": 1.5150,
                "position_size": 1.0,
            },
            "outcome": {"r_multiple": 2.5, "pnl_usd": 250.0},
        }
        candles = [
            make_candle(1.5000, 1.5100, 1.4950, 1.5050, time="2024-01-15T14:00:00Z")
        ]
        htf_candles = [make_candle(1.5000, 1.5200, 1.4900, 1.5050)]

        result = enricher.enrich(trade, candles, htf_candles)
        # NY AM killzone should be flagged as killzone
        if result.time_window in {
            "NY_AM_KILLZONE",
            "NY_AM_SILVER_BULLET",
            "LONDON_KILLZONE",
            "LONDON_SILVER_BULLET",
            "NY_PM_KILLZONE",
            "NY_PM_SILVER_BULLET",
        }:
            assert result.is_killzone is True
