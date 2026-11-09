# Requirements Document

**Spec**: Algo Mind

## Introduction

The engine is a static robot. It reads the trader's concepts (time, premium and discount, equilibrium, liquidity, inefficiencies, displacement and liquidation) through rules we wrote. It combines them with weights we guessed, and it fires on both sides of every range. On the search's unread years, every hand-written way of combining the concepts called direction at a random walk's rate:
- the chain (H-K);
- the stack (H-M);
- the turtle soup (H-U);
- the sides above (H-V);
- candle sentiment (H-X).

H-N's trades take both sides on 97% of market-days. With the week's real direction and stops of ten spreads or more, the same trades would make +0.16 to +0.19R. **The missing piece is the side, called once a week, and calling it right 57-60% of the time clears the costs.**

The trader (2026-10-29): no single concept carries direction. It lives in how they combine, "time then price", like a puzzle. H-Y let the data search the combinations at the weekly open, on decades of daily history. Its confident thirds called the next week +2.9 points above drift on weeks it had never seen (53.1%), up and down alike, with time (the month of the quarter, the quarter) as the inputs it leaned on most. That is the first lean any combination of these concepts has shown. It is not proven, and not enough.

**Algo Mind is the brain the engine lacks.** The concepts stay the same. What changes is who decides how they combine, and how that is checked:
- **Senses:** the engine's concepts, read with the trader's definitions into a weekly state of time and price.
- **Brain:** a model learned from what followed each state, giving a side and its probability, or no side.
- **Memory:** the past weeks most like this one, and what they did.
- **The trader:** their weekly call beside the brain's, both scored.
- **Hands:** the existing execution, trading only the side it is given.
- **Learning:** refits judged only on the weeks after them.

**Guiding constraints:**
- **Evidence before trust.** The brain trades on paper only, beside the controls, until its calls clear the bar on weeks it never saw.
- **The search's test window stays unread.** The brain is fitted on weeks before 2023-01-01, and its live states are read from 2025-01-01 on. Nothing from 2023-2024 is downloaded or read.
- **One definition of each concept.** The senses are H-Y's state code (`algo_research/search_state.py`), so the brain sees live what it learned on.

---

## Glossary

- **Week**: Monday to Friday by date. Its open is the first day's open.
- **State**: the time and price features at a week's open, from candles closed before it (H-Y's features).
- **Brain call**: BULLISH or BEARISH when the brain's probability is in its fitted probabilities' top or bottom third; otherwise NONE.
- **Brief**: the brain's state, probability, call and analogs for every market in one week.
- **Model version**: a fitted brain with its training window, features, settings and fitted thresholds.

---

## Requirements

### Requirement 1: The Senses

**User Story:** As the trader, I want the brain to read the market with my concepts and my definitions, the same way in its training and live, so that what it learned applies to the week in front of it.

#### Acceptance Criteria

1. THE senses SHALL be H-Y's weekly state (`algo_research.search_state`):
   - **time:** the quarter, the month of the quarter, the week of the month, a month or quarter opening, and the opening gap;
   - **price, for MN1, W1 and D1:** the last closed candle's shape and size, the two-candle read, consecutive closes, premium or discount, and the distance to untaken liquidity and to unfilled FVGs.

   Each is read from candles closed before the week's open.
2. THE live state SHALL be read from Yahoo's daily bars from 2025-01-01 to the day before the run, cleaned as for training (an FX day closes at the next day's open). A day not yet closed is left out.
3. A state whose last closed day is before the Friday before its week SHALL be marked provisional.

### Requirement 2: The Brain

**User Story:** As the trader, I want a model that turns the weekly state into a side with its probability, or no side, so that the engine has a reason for each side it trades.

#### Acceptance Criteria

1. THE brain SHALL be H-Y's model with its settings unchanged (gradient-boosted trees, depth 3, 200 iterations), fitted on every week before 2023-01-01, weighted so each market's up and down weeks weigh the same.
2. A MODEL VERSION SHALL be saved with:
   - its training window and number of weeks;
   - its features and settings;
   - its fitted thresholds (the 33rd and 67th percentiles of its training probabilities);
   - the code's commit.

   Fitting twice on the same data SHALL give the same probabilities.
3. FOR a week and market, the brain SHALL give its probability of an up week and its call.

### Requirement 3: Memory

**User Story:** As the trader, I want to see the past weeks that looked most like this one and what they did, so that I can judge the brain's lean the way I judge a chart.

#### Acceptance Criteria

1. FOR a state, MEMORY SHALL give the 20 training weeks nearest to it on the standardized state, across markets, with:
   - their market and week;
   - how they closed;
   - the share that closed up.
2. THE analogs SHALL be drawn only from the brain's training weeks.

### Requirement 4: The Brief and the Trader

**User Story:** As the trader, I want the brain's call beside mine on the context page, so that each week shows whether I beat the bar and whether I beat the machine.

#### Acceptance Criteria

1. A BRIEF SHALL be written for a week (`python -m algo_mind brief --week YYYY-MM-DD`): each market's state, probability, call and analogs, the model version, and whether it is provisional.
2. THE context page SHALL show, for each market, the brain's call, its probability and the analogs' up share, beside the trader's call.
3. THE scorecard SHALL score the brain's calls as it scores the trader's, with totals for:
   - the trader;
   - the brain;
   - the two agreeing.

### Requirement 5: The Hands

**User Story:** As the trader, I want the execution to trade only a given side, from me, from the brain, or from both agreeing, each on paper beside the controls, so that the source of the side is the only difference between them.

#### Acceptance Criteria

1. A brief SHALL write the brain's thesis file. Saving a call or a brief SHALL write the agreement's thesis file, holding only the markets where the trader and the brain call the same side, with the trader's draw and protected swing.
2. THE configuration SHALL have the brain's and the agreement's variants: the context variant with their thesis files.
3. A paper agent SHALL run each, on the controls' markets.

### Requirement 6: The Bench

**User Story:** As the trader, I want to know how often a brain like this finds an edge that isn't there, and how big an edge it can find at our sample sizes, so that I know what its results mean.

#### Acceptance Criteria

1. ON random walks with the markets' own volatility and history lengths, the same fit and judgment SHALL be repeated (at least 20 runs). The bench SHALL report how often the judged thirds beat drift as much as H-Y's +2.9 points.
2. WITH a planted effect (a state feature shifting the week's direction by a known amount), the bench SHALL report how often it is found.

### Requirement 7: Learning

**User Story:** As the trader, I want the brain to learn from the weeks as they come, without fooling itself, so that it improves only where the improvement holds.

#### Acceptance Criteria

1. A REFIT SHALL add the weeks since the last version's training window. It is a candidate until it has been judged on later weeks it didn't see, against the version in use, on the same weeks.
2. EVERY refit and judgement SHALL be logged in a ledger: the version, its window, the weeks judged and the result. A candidate replaces the version in use only when it does better there.
3. THE third look: the brain's calls on the weeks of 2026 its live state can read SHALL be reported as information. They change nothing.
