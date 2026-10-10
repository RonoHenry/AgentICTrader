# H990: Golden: an Asian range raid, reclaimed, runs to the other side

- **FAIL** · win_rate 0.1613 [0.0385, 0.2857] · coin_flip 0.1712, random_time 0.1724 · 31 events on 19 dates (confirm slice)

## The question as registered

sha256 `287a0c9322810e6ac10bb6acd66bc862317de0dbab16f50acd84e74cad0dee3e`

```toml
# The golden research run's hypothesis (task 255): a fixed question on fixed synthetic data.
# Its report and ledger row must be byte-identical on every run (Requirement 14.3).
id = "H990"
title = "Golden: an Asian range raid, reclaimed, runs to the other side"
statement = """
After London trades through one side of the Asian range and an M15 bar closes back inside,
price reaches the range's other side before the raid's extreme. Synthetic data: no edge.
"""
family = "golden"
created = 2026-10-10

[event]
name = "asia_raid_reclaim"
params = { window = ["00:00", "12:00"], reclaim_within = 4 }

[measure]
kind = "race"

[trade]
stop = { kind = "level", name = "raid_extreme" }
target = { kind = "level", name = "asia_opposite" }
time_limit = "day_close"

[baselines]
use = ["coin_flip", "random_time"]

[pass]
min_events = 10
min_days = 5
require = [
  { stat = "win_rate", versus = "coin_flip" },
  { stat = "win_rate", versus = "random_time" },
  { stat = "mean_net_r" },
]
```

## Results

### Sample

- Events: 31 fired, 31 measured, on 19 trading dates.
- Skipped: draw_null_level 68.
- By instrument: EURUSD 15, XAUUSD 16.
- By year: 2025 31.
- By weekday: Mon 7, Tue 4, Wed 6, Thu 8, Fri 6.
- Random-time draws per event: 5 to 5; 0 event(s) had fewer than the most.

### Results

| Statistic | Versus | Value | Baseline | Tested [95% interval] | Rule | Result |
|---|---|---|---|---|---|---|
| win_rate | coin_flip | 0.1613 | 0.1712 | difference -0.0099 [-0.1136, 0.1001] | lower bound > 0 | fail |
| win_rate | random_time | 0.1613 | 0.1724 | difference -0.0111 [-0.1616, 0.1212] | lower bound > 0 | fail |
| mean_net_r | – | -0.7330 | – | value -0.7330 [-1.0429, -0.3979] | lower bound > 0 | fail |

Every statistic of the measure, alone:

| Statistic | Value [95% interval] |
|---|---|
| win_rate | 0.1613 [0.0385, 0.2857] |
| mean_net_r | -0.7330 [-1.0429, -0.3979] |
| mean_gross_r | -0.1406 [-0.4392, 0.1773] |

### Stability

The tested comparison per group (these inform; only the rules decide).

| Instrument | Events | Dates | Value | Baseline | Effect |
|---|---|---|---|---|---|
| EURUSD | 15 | 15 | 0.0667 | 0.1302 | -0.0635 |
| XAUUSD | 16 | 16 | 0.2500 | 0.2097 | 0.0403 |

| Quarter | Events | Dates | Value | Baseline | Effect |
|---|---|---|---|---|---|
| 2025Q1 | 31 | 19 | 0.1613 | 0.1712 | -0.0099 |

| Weekday | Events | Dates | Value | Baseline | Effect |
|---|---|---|---|---|---|
| Mon | 7 | 4 | 0.1429 | 0.2177 | -0.0748 |
| Tue | 4 | 3 | 0.0000 | 0.1854 | -0.1854 |
| Wed | 6 | 4 | 0.0000 | 0.1180 | -0.1180 |
| Thu | 8 | 4 | 0.2500 | 0.1966 | 0.0534 |
| Fri | 6 | 4 | 0.3333 | 0.1270 | 0.2064 |

Quarters with the overall effect's sign: 1.00.

### Races

- Outcomes: STOP 26, TARGET 5.
- Ambiguous bars (one M1 bar reached both stop and target; the stop won): 0.000.
- Holding time: mean 27.4 minutes.
- MFE (R) quartiles: -0.25, -0.02, 0.78; MAE (R) quartiles: -1.00, -1.00, -1.00.

### Check by eye

The first 20 events per instrument. Times are the M15 close the event fired on.

**EURUSD**

| t (UTC) | New York | Direction | raid_extreme | asia_opposite | smt | race_stop | race_target | race_outcome |
|---|---|---|---|---|---|---|---|---|
| 2025-01-20 05:15 | Mon 00:15 | SHORT | 1.09930 | 1.09870 | – | 1.09930 | 1.09870 | TARGET |
| 2025-01-21 06:15 | Tue 01:15 | LONG | 1.09458 | 1.09520 | – | 1.09458 | 1.09520 | STOP |
| 2025-01-22 06:00 | Wed 01:00 | SHORT | 1.09124 | 1.09011 | – | 1.09124 | 1.09011 | STOP |
| 2025-01-23 09:30 | Thu 04:30 | SHORT | 1.09321 | 1.09162 | – | 1.09321 | 1.09162 | STOP |
| 2025-01-24 05:15 | Fri 00:15 | SHORT | 1.09123 | 1.09053 | – | 1.09123 | 1.09053 | STOP |
| 2025-01-27 05:45 | Mon 00:45 | LONG | 1.08581 | 1.08724 | – | 1.08581 | 1.08724 | STOP |
| 2025-01-28 05:15 | Tue 00:15 | SHORT | 1.08785 | 1.08678 | – | 1.08785 | 1.08678 | STOP |
| 2025-01-29 05:45 | Wed 00:45 | SHORT | 1.08941 | 1.08816 | – | 1.08941 | 1.08816 | STOP |
| 2025-01-30 06:15 | Thu 01:15 | LONG | 1.09009 | 1.09129 | – | 1.09009 | 1.09129 | STOP |
| 2025-02-05 05:30 | Wed 00:30 | SHORT | 1.08916 | 1.08801 | – | 1.08916 | 1.08801 | STOP |
| 2025-02-06 05:30 | Thu 00:30 | LONG | 1.09321 | 1.09423 | – | 1.09321 | 1.09423 | STOP |
| 2025-02-10 05:15 | Mon 00:15 | SHORT | 1.09587 | 1.09501 | – | 1.09587 | 1.09501 | STOP |
| 2025-02-12 06:00 | Wed 01:00 | SHORT | 1.09691 | 1.09601 | – | 1.09691 | 1.09601 | STOP |
| 2025-02-13 05:15 | Thu 00:15 | LONG | 1.09753 | 1.09826 | – | 1.09753 | 1.09826 | STOP |
| 2025-02-14 05:30 | Fri 00:30 | SHORT | 1.10058 | 1.09971 | – | 1.10058 | 1.09971 | STOP |

**XAUUSD**

| t (UTC) | New York | Direction | raid_extreme | asia_opposite | smt | race_stop | race_target | race_outcome |
|---|---|---|---|---|---|---|---|---|
| 2025-01-20 06:00 | Mon 01:00 | SHORT | 2621.67137 | 2620.02754 | – | 2621.67137 | 2620.02754 | STOP |
| 2025-01-23 05:15 | Thu 00:15 | SHORT | 2614.37031 | 2611.56813 | – | 2614.37031 | 2611.56813 | STOP |
| 2025-01-24 05:45 | Fri 00:45 | SHORT | 2619.64654 | 2616.03884 | – | 2619.64654 | 2616.03884 | STOP |
| 2025-01-27 05:15 | Mon 00:15 | SHORT | 2617.40425 | 2615.43207 | – | 2617.40425 | 2615.43207 | STOP |
| 2025-01-28 06:15 | Tue 01:15 | LONG | 2611.79245 | 2614.43885 | – | 2611.79245 | 2614.43885 | STOP |
| 2025-01-29 06:45 | Wed 01:45 | LONG | 2610.99767 | 2613.57898 | – | 2610.99767 | 2613.57898 | STOP |
| 2025-01-30 05:30 | Thu 00:30 | SHORT | 2603.59031 | 2601.11867 | – | 2603.59031 | 2601.11867 | TARGET |
| 2025-01-31 06:00 | Fri 01:00 | LONG | 2595.96000 | 2598.47558 | – | 2595.96000 | 2598.47558 | STOP |
| 2025-02-03 07:00 | Mon 02:00 | SHORT | 2586.91161 | 2585.10287 | – | 2586.91161 | 2585.10287 | STOP |
| 2025-02-04 05:30 | Tue 00:30 | LONG | 2582.83870 | 2584.91602 | – | 2582.83870 | 2584.91602 | STOP |
| 2025-02-06 08:15 | Thu 03:15 | SHORT | 2589.66076 | 2586.36888 | – | 2589.66076 | 2586.36888 | TARGET |
| 2025-02-07 09:45 | Fri 04:45 | SHORT | 2590.60377 | 2586.87309 | – | 2590.60377 | 2586.87309 | TARGET |
| 2025-02-10 07:00 | Mon 02:00 | LONG | 2590.84944 | 2592.97492 | – | 2590.84944 | 2592.97492 | STOP |
| 2025-02-12 05:15 | Wed 00:15 | SHORT | 2609.86247 | 2607.31128 | – | 2609.86247 | 2607.31128 | STOP |
| 2025-02-13 05:15 | Thu 00:15 | LONG | 2609.75169 | 2612.60868 | – | 2609.75169 | 2612.60868 | STOP |
| 2025-02-14 05:45 | Fri 00:45 | SHORT | 2615.02115 | 2612.84057 | – | 2615.02115 | 2612.84057 | TARGET |

## Inputs

- Snapshot: `golden`
  - EURUSD: simulated
  - XAUUSD: simulated
- Code commit: `0000000000000000000000000000000000000000`
- Costs (spec file):
  - EURUSD: typical spread 0.0001
  - XAUUSD: typical spread 0.2
- H990: slice confirm, seed 2916657534754426474; ledger row 1
