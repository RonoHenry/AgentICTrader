export interface HTFProjections {
  htf_timeframe: string
  htf_open: number
  htf_high: number
  htf_low: number
  open_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  htf_high_proximity_pct: number
  htf_low_proximity_pct: number
  htf_body_pct: number
  htf_upper_wick_pct: number
  htf_lower_wick_pct: number
  htf_close_position: number
}

export interface Setup {
  id: string
  instrument: string
  timeframe: string
  time: string
  regime: string
  patterns: string[]
  confidence_score: number
  htf_projections: HTFProjections
  entry_price: number | null
  sl_price: number | null
  tp_price: number | null
  reasoning?: string
  time_window?: string
  narrative_phase?: string
}

export interface AgentStatus {
  healthy: boolean
  kill_switch_active: boolean
}

export interface RiskExposure {
  daily_dd_pct: number
  weekly_dd_pct: number
  open_trades: number
  equity: number
}

export interface EdgeMetrics {
  win_rate: number
  avg_r_multiple: number
  expectancy: number
  trade_count: number
  total_pnl: number
  avg_pnl: number
}

export interface EquityPoint {
  timestamp: string
  cumulative_pnl: number
  trade_id: string
  r_multiple: number
}

export interface TradeJournalEntry {
  trade_id: string
  instrument: string
  direction: 'BUY' | 'SELL'
  entry_price: number
  exit_price: number
  r_multiple: number
  pnl_usd: number
  session: string
  htf_open_bias: string
  entry_time: string
  exit_time: string
}

export interface DecisionLogEntry {
  id: string
  timestamp: string
  instrument: string
  decision: 'TAKEN' | 'SKIPPED' | 'NOTIFIED'
  confidence: number
  reasoning: string
  regime: string
  patterns: string[]
}
