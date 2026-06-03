"""
Re-export of the Kafka producer from services/market-data/kafka_producer.py.
"""
import importlib.util as _util
import os as _os

_path = _os.path.join(
    _os.path.dirname(_os.path.dirname(__file__)),
    "market-data",
    "kafka_producer.py",
)
_spec = _util.spec_from_file_location("services._market_data_kafka_producer", _path)
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

KafkaProducer = _mod.KafkaProducer
TickMessage = _mod.TickMessage
CandleMessage = _mod.CandleMessage
TOPIC_TICKS = _mod.TOPIC_TICKS
TOPIC_CANDLES = _mod.TOPIC_CANDLES

__all__ = [
    "KafkaProducer",
    "TickMessage",
    "CandleMessage",
    "TOPIC_TICKS",
    "TOPIC_CANDLES",
]
