"""
Kafka consumer: market.candles -> LiquidityMappingEngine.analyze() -> liquidity.analyzed

Maintains a bounded per-instrument, per-timeframe candle buffer. Every
completed candle is appended to its buffer; once an instrument has both D1
and W1 history buffered (the engine's minimum requirement), a fresh analysis
is run and republished.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, LiquidityMap, Timeframe

logger = logging.getLogger(__name__)

TOPIC_CANDLES = "market.candles"
TOPIC_LIQUIDITY_ANALYZED = "liquidity.analyzed"

_REQUIRED_TIMEFRAMES = (Timeframe.D1, Timeframe.W1)


class LiquidityKafkaConsumer:
    """Consumes completed candles and republishes a fresh LiquidityMap per update."""

    def __init__(self, bootstrap_servers: str, max_candles_per_tf: int = 200):
        self.bootstrap_servers = bootstrap_servers
        self.max_candles_per_tf = max_candles_per_tf
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._producer: Optional[AIOKafkaProducer] = None
        self._buffers: Dict[str, Dict[Timeframe, List[Candle]]] = {}
        self._engine = LiquidityMappingEngine()

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(TOPIC_CANDLES, bootstrap_servers=self.bootstrap_servers)
        self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self._consumer.start()
        await self._producer.start()

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
        if self._producer is not None:
            await self._producer.stop()

    async def run_forever(self) -> None:
        assert self._consumer is not None, "call start() first"
        async for message in self._consumer:
            payload = json.loads(message.value.decode("utf-8"))
            await self.handle_message(payload)

    async def handle_message(self, payload: dict) -> Optional[LiquidityMap]:
        """Process one market.candles payload. Returns the published LiquidityMap,
        or None if the candle was malformed or there isn't yet enough buffered
        history (D1 + W1) to run analyze()."""
        candle = self._parse_candle(payload)
        if candle is None:
            return None

        instrument = payload["instrument"]
        buffer = self._buffers.setdefault(instrument, {})
        candles = buffer.setdefault(candle.timeframe, [])
        candles.append(candle)
        if len(candles) > self.max_candles_per_tf:
            del candles[: len(candles) - self.max_candles_per_tf]

        if not all(buffer.get(tf) for tf in _REQUIRED_TIMEFRAMES):
            return None

        try:
            liquidity_map = self._engine.analyze(buffer, instrument, candle.timestamp)
        except ValueError:
            return None

        await self._publish(instrument, liquidity_map)
        return liquidity_map

    def _parse_candle(self, payload: dict) -> Optional[Candle]:
        try:
            tf = Timeframe(payload["timeframe"])
            raw_ts = payload["time"]
            timestamp = datetime.fromisoformat(raw_ts) if isinstance(raw_ts, str) else raw_ts
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return Candle(
                timestamp=timestamp, open=payload["open"], high=payload["high"],
                low=payload["low"], close=payload["close"], volume=payload.get("volume"),
                timeframe=tf, instrument=payload["instrument"],
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed market.candles message: %s", exc)
            return None

    async def _publish(self, instrument: str, liquidity_map: LiquidityMap) -> None:
        assert self._producer is not None, "call start() first"
        key = instrument.encode("utf-8")
        value = json.dumps(liquidity_map.model_dump(mode="json")).encode("utf-8")
        await self._producer.send(TOPIC_LIQUIDITY_ANALYZED, key=key, value=value)
