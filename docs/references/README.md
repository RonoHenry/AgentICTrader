# Reference Materials

This folder contains source educational materials and frameworks that inform the
AgentICTrader platform design, methodology, and implementation.

## Contents

Place your reference PDFs and documents here. Suggested naming convention:

```
ttrades_<topic>.pdf          — Ttrades educational template materials
ict_<topic>.pdf              — ICT (Inner Circle Trader) methodology resources
<source>_<topic>.<ext>       — Any other reference materials
```

## How These Are Used

Once documents are added here, they can be:

1. **Dragged into a Kiro chat session** to directly compare against the current
   implementation and identify gaps or misalignments.

2. **Used to improve the ML labellers** — particularly:
   - `ml/models/pattern_detector/labeller.py` — pattern detection rules
   - `ml/models/confluence_scorer/train.py` — confluence scoring heuristics

3. **Used to validate ICT terminology and logic** against what is encoded in:
   - `ml/features/zone_features.py` — Premium/Discount/PD Array detection
   - `ml/features/session_features.py` — Killzone and Silver Bullet windows
   - `ml/features/htf_projections.py` — HTF candle projection logic
   - `backend/trader/agents/pd_array/` — PD Array agents
   - `backend/trader/agents/cisd.py` — CISD logic

4. **Used as a source of ground truth** for backtesting setups and seeding the
   RAG pipeline (Qdrant collection) with historically validated trade examples.

## Priority Areas for Gap Analysis

When reviewing the Ttrades materials against this codebase, focus on:

| Area | Current Implementation | What to Check |
|---|---|---|
| Entry criteria | Heuristic labeller (score ≥ 3.5) | Does Ttrades define specific entry rules? |
| Trade management | Partial close at 1R, SL to BE | Does Ttrades use a different R management framework? |
| Killzone definitions | London, NY AM, NY PM, Silver Bullets | Are Ttrades session windows identical? |
| PD Array hierarchy | OB > FVG > Breaker > IFVG | Does Ttrades rank arrays differently? |
| Confluence criteria | 5 signals scored | Does Ttrades have a specific confluence checklist? |
| Liquidity concepts | Sweep detection only | Does Ttrades cover inducement or turtle soup patterns? |
