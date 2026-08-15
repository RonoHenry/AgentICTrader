"""
Fire-and-forget persistence of every rendered chart + its VisualAnalysis
label, so a corpus accumulates for Phase 4/5 without any manual work.

Scheduled via FastAPI's BackgroundTasks from api/router.py - Starlette runs
background tasks after the HTTP response has already been sent, so this
never adds latency to /visual/analyse and a storage failure here can never
surface as an error to the caller.

Does NOT compute or store any embedding, and does NOT invoke any model
training - that is Phase 4/5, out of scope for this spec (see
.kiro/specs/visual-model/design.md, Non-Goals). The only images this module
ever persists are ones rendered by this same service from the platform's own
OHLCV data - there is no separate ingestion path for externally sourced
images.

**Validates: Requirements 11.1-11.4 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from services.visual_model.config import settings
from services.visual_model.schemas.visual_analysis import VisualAnalysis

logger = logging.getLogger(__name__)

try:
    import boto3

    _BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore[assignment]

_s3_client_singleton: Optional[object] = None


def _get_s3_client() -> Optional[object]:
    global _s3_client_singleton
    if _s3_client_singleton is None and _BOTO3_AVAILABLE:
        try:
            _s3_client_singleton = boto3.client("s3")
        except Exception as exc:  # pragma: no cover
            logger.warning("training data pipeline: failed to init S3 client: %s", exc)
            _s3_client_singleton = None
    return _s3_client_singleton


def store_training_sample(
    chart_png: bytes,
    analysis: VisualAnalysis,
    instrument: str,
    timestamp: datetime,
    s3_client: Optional[object] = None,
) -> None:
    """Persist a chart render + its VisualAnalysis label to S3.

    Never raises - by the time this runs, the HTTP response has already been
    sent, so nothing is listening for an exception here.
    """
    client = s3_client if s3_client is not None else _get_s3_client()
    if client is None:
        logger.warning(
            "training data pipeline: no S3 client configured, skipping sample storage"
        )
        return

    base_key = f"visual-samples/{instrument}/{timestamp.isoformat().replace(':', '-')}"
    try:
        client.put_object(
            Bucket=settings.s3_bucket_charts,
            Key=f"{base_key}.png",
            Body=chart_png,
            ContentType="image/png",
        )
        client.put_object(
            Bucket=settings.s3_bucket_charts,
            Key=f"{base_key}.json",
            Body=analysis.model_dump_json(),
            ContentType="application/json",
        )
    except Exception as exc:
        logger.warning("training data pipeline: failed to store sample %s: %s", base_key, exc)
