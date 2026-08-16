"""Liquidity Engine microservice: FastAPI wrapper + Kafka consumer around
pd_array_engine.LiquidityMappingEngine. Optional (Task 162) — the engine
itself has zero I/O and is consumed in-process by agent/nodes/observe_node.py;
this service exists for callers that need it over HTTP or via Kafka instead.
"""
