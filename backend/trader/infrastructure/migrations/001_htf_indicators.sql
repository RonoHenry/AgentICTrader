-- =============================================================================
-- Migration: 001_htf_indicators.sql
-- Purpose:   Replace legacy ATR/RSI/ADX/EMA indicator columns in the
--            `indicators` table with HTF Candle Projection columns.
--
-- Background:
--   The original schema included ATR, RSI, ADX, EMA, and volume indicator
--   columns that are no longer used. The HTF Candle Projections indicator is
--   the SOLE technical indicator in this system. This migration drops the
--   legacy columns and adds the new HTF projection columns in their place.
--
-- Apply to a running database with:
--   psql -U agentictrader -d agentictrader -f 001_htf_indicators.sql
-- =============================================================================

BEGIN;

-- ── Drop legacy indicator columns ────────────────────────────────────────────
ALTER TABLE indicators DROP COLUMN IF EXISTS atr_14;
ALTER TABLE indicators DROP COLUMN IF EXISTS atr_pct;
ALTER TABLE indicators DROP COLUMN IF EXISTS rsi_14;
ALTER TABLE indicators DROP COLUMN IF EXISTS adx_14;
ALTER TABLE indicators DROP COLUMN IF EXISTS ema_50;
ALTER TABLE indicators DROP COLUMN IF EXISTS ema_200;
ALTER TABLE indicators DROP COLUMN IF EXISTS volume_sma_20;
ALTER TABLE indicators DROP COLUMN IF EXISTS volume_delta;

-- ── Add HTF Candle Projection columns ────────────────────────────────────────
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_timeframe          VARCHAR(5);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_open               NUMERIC(18, 5);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_high               NUMERIC(18, 5);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_low                NUMERIC(18, 5);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_open_bias          VARCHAR(10)
    CHECK (htf_open_bias IN ('BULLISH', 'BEARISH', 'NEUTRAL'));
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_high_proximity_pct NUMERIC(8, 4);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_low_proximity_pct  NUMERIC(8, 4);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_body_pct           NUMERIC(8, 4);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_upper_wick_pct     NUMERIC(8, 4);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_lower_wick_pct     NUMERIC(8, 4);
ALTER TABLE indicators ADD COLUMN IF NOT EXISTS htf_close_position     NUMERIC(8, 4);

COMMIT;
