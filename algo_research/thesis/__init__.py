"""The thesis developer (market-narrative update 2026-10-22, Requirements 16-17).

A reasoning model reads what the engine and the trader's Fractal + POI indicator see at a trading day's 17:00 open,
blind (no date, no market name, prices rescaled), and gives the day's thesis: bias, draw, invalidation, or none.

    llm.py      the OpenAI-compatible client (OpenRouter by default), cached and budgeted
    facts.py    the blind facts at the open
    prompt.py   the procedure sent to the model, and the answer's fixed form
"""
