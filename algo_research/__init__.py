"""AlgoResearch: does a market condition predict what price does next, better than chance?

An offline research lab beside AlgoBacktester (.kiro/specs/algo-research). It
asks questions written down first (hypotheses), at the moments the engine
decides (every M15 close), on a frozen snapshot of the study's candles, and
answers with baselines and day-clustered intervals. Nothing live imports it.

    python -m algo_research snapshot | build | explore H002 | run H002 | ledger
"""
