-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── CANDLES ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candles (
    time            TIMESTAMPTZ     NOT NULL,
    instrument      VARCHAR(20)     NOT NULL,
    timeframe       VARCHAR(5)      NOT NULL,
    open            NUMERIC(18, 5)  NOT NULL,
    high            NUMERIC(18, 5)  NOT NULL,
    low             NUMERIC(18, 5)  NOT NULL,
    close           NUMERIC(18, 5)  NOT NULL,
    volume          BIGINT,
    spread          NUMERIC(10, 5),
    complete        BOOLEAN         DEFAULT TRUE,
    source          VARCHAR(20),
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (time, instrument, timeframe)
);

SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_instrument_tf_time ON candles (instrument, timeframe, time DESC);
CREATE INDEX IF NOT EXISTS idx_candles_instrument_time ON candles (instrument, time DESC);

-- ── TICKS ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticks (
    time        TIMESTAMPTZ     NOT NULL,
    instrument  VARCHAR(20)     NOT NULL,
    bid         NUMERIC(18, 5)  NOT NULL,
    ask         NUMERIC(18, 5)  NOT NULL,
    volume      INTEGER,
    source      VARCHAR(20)
);

SELECT create_hypertable('ticks', 'time', if_not_exists => TRUE);
SELECT add_retention_policy('ticks', INTERVAL '90 days', if_not_exists => TRUE);

-- ── INDICATORS ───────────────────────────────────────────────────────────────
-- HTF Candle Projections is the SOLE technical indicator in this system.
-- No ATR, RSI, ADX, EMA, or volume indicators are used.
CREATE TABLE IF NOT EXISTS indicators (
    time                    TIMESTAMPTZ     NOT NULL,
    instrument              VARCHAR(20)     NOT NULL,
    timeframe               VARCHAR(5)      NOT NULL,
    session                 VARCHAR(15),
    day_of_week             SMALLINT,
    is_news_window          BOOLEAN         DEFAULT FALSE,
    -- HTF Candle Projection columns
    htf_timeframe           VARCHAR(5),
    htf_open                NUMERIC(18, 5),
    htf_high                NUMERIC(18, 5),
    htf_low                 NUMERIC(18, 5),
    htf_open_bias           VARCHAR(10)     CHECK (htf_open_bias IN ('BULLISH', 'BEARISH', 'NEUTRAL')),
    htf_high_proximity_pct  NUMERIC(8, 4),
    htf_low_proximity_pct   NUMERIC(8, 4),
    htf_body_pct            NUMERIC(8, 4),
    htf_upper_wick_pct      NUMERIC(8, 4),
    htf_lower_wick_pct      NUMERIC(8, 4),
    htf_close_position      NUMERIC(8, 4)
);

SELECT create_hypertable('indicators', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_indicators_instrument_tf_time ON indicators (instrument, timeframe, time DESC);

-- ── ECONOMIC EVENTS ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS economic_events (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    event_time      TIMESTAMPTZ     NOT NULL,
    currency        VARCHAR(5)      NOT NULL,
    event_name      VARCHAR(200)    NOT NULL,
    impact          VARCHAR(10)     NOT NULL CHECK (impact IN ('LOW', 'MEDIUM', 'HIGH')),
    forecast        VARCHAR(50),
    previous        VARCHAR(50),
    actual          VARCHAR(50),
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_time_currency ON economic_events (event_time, currency);
CREATE INDEX IF NOT EXISTS idx_events_time_impact ON economic_events (event_time, impact);
