#!/usr/bin/env python3
"""
Prepare and enrich historical trading setups for AlgoRAG.

Usage:
    python scripts/rag/prepare_historical_setups.py [--limit N] [--output OUTPUT_PATH]

This script:
1. Loads historical trades from MongoDB trade_journal
2. Fetches corresponding candles for each trade
3. Enriches each trade with HTF/PD array/session context
4. Generates narratives
5. Saves enriched setups to JSON
"""
import argparse
import json
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure workspace root is on the path
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.rag.utils.setup_enricher import SetupEnricher  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stub data loaders (replace with real MongoDB / TimescaleDB calls)
# ---------------------------------------------------------------------------


def load_sample_trades(limit: int = 10) -> List[Dict[str, Any]]:
    """Load sample trades (stub for MongoDB integration)."""
    base_time = "2024-01-15T09:15:00Z"
    trades = []
    for i in range(min(limit, 10)):
        entry_price = 1.5000 + i * 0.0010
        trades.append(
            {
                "trade_id": f"TRD-SAMPLE-{i + 1:03d}",
                "instrument": "EURUSD",
                "direction": "BUY" if i % 2 == 0 else "SELL",
                "entry": {"time": base_time, "price": entry_price},
                "exit": {
                    "time": "2024-01-15T11:00:00Z",
                    "price": entry_price + 0.0050,
                },
                "risk": {
                    "stop_loss": entry_price - 0.0020,
                    "take_profit": entry_price + 0.0060,
                    "position_size": 1.0,
                },
                "outcome": {"r_multiple": 2.5 if i % 2 == 0 else -1.0, "pnl_usd": 250.0},
            }
        )
    return trades


def generate_sample_candles(entry_time: Optional[str], n: int = 20) -> List[Dict[str, Any]]:
    """Generate synthetic candles for testing (stub for TimescaleDB integration)."""
    candles = []
    base_price = 1.5000
    for i in range(n):
        open_ = base_price + i * 0.0001
        candles.append(
            {
                "time": entry_time or "2024-01-15T09:00:00Z",
                "open": open_,
                "high": open_ + 0.0010,
                "low": open_ - 0.0005,
                "close": open_ + 0.0005,
                "volume": 1000,
            }
        )
    return candles


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main(limit: int = 100, output_path: str = "data/enriched_setups.json"):
    logging.basicConfig(level=logging.INFO)
    enricher = SetupEnricher(htf_timeframe="H1")

    logger.info(f"Loading up to {limit} historical trades...")
    trades = load_sample_trades(limit)

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for trade in trades:
        try:
            entry_time = trade.get("entry", {}).get("time") or trade.get("entry_time")
            candles = generate_sample_candles(entry_time)
            htf_candles = generate_sample_candles(entry_time, n=5)

            enriched = enricher.enrich(trade, candles, htf_candles)
            results.append(enriched.model_dump(mode="json"))
        except Exception as e:
            logger.warning(f"Failed to enrich trade {trade.get('trade_id')}: {e}")
            errors.append({"trade_id": trade.get("trade_id"), "error": str(e)})

    # Save results
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(
        f"Enriched {len(results)} setups, {len(errors)} errors. Saved to {output_path}"
    )
    return results, errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare and enrich historical trading setups for AlgoRAG."
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="data/enriched_setups.json")
    args = parser.parse_args()
    main(args.limit, args.output)
