"""The feature table: facts known at each decision time t (Requirements 3-5).

- ``market``: facts read off the chart, vectorised over M1 and calendar bars;
- ``anticipation``: the engine's anticipation of each D1 candle;
- ``engine`` (stage 2): what the engine saw and decided at every close;
- ``cache``: Parquet entries keyed by the data and code they depend on.

Nothing here imports algo_research.labels: what happened after t can't leak
into a condition (Requirement 6.1).
"""
