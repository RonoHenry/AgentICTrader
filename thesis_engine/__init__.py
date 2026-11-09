"""The Thesis Engine: AlgoMindDIS's Setup Engine, built as a state machine (.kiro/specs/thesis-engine).

One machine per market, stepped by candle closes: FLAT → THESIS → AT_LEVEL → ARMED → IN_TRADE → SPENT, and back to
FLAT when the thesis ends. The side only ever comes in with a thesis; the pools, arrays and ranges are AlgoMindDIS's.
"""
VERSION = "v1"
