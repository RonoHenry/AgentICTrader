"""The blind replay: the trader's daily reads, as of the open, scored (market-narrative Requirement 10).

    python -m algo_research.replay [--instrument XAUUSD] [--port 8765] [--no-browser]

It reads the narrative for the reveal and decides nothing, so it sits outside
Requirement 5's guard. Reads are stored under data/journal/blind/, which git ignores.
"""
from algo_research.replay.bars import ReplayBars
from algo_research.replay.journal import Journal, ReplayError, day_order
from algo_research.replay.scoring import score_thesis, score_trade, summarize
from algo_research.replay.server import ReplayApp, make_server

__all__ = ["Journal", "ReplayApp", "ReplayBars", "ReplayError", "day_order", "make_server", "score_thesis",
           "score_trade", "summarize"]
