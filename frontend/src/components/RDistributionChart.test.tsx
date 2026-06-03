import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RDistributionChart } from './RDistributionChart'
import type { TradeJournalEntry } from '@/types'

function makeEntry(
  r_multiple: number,
  overrides: Partial<TradeJournalEntry> = {}
): TradeJournalEntry {
  return {
    trade_id: `trade-${Math.random()}`,
    instrument: 'EURUSD',
    direction: r_multiple >= 0 ? 'BUY' : 'SELL',
    entry_price: 1.085,
    exit_price: 1.09,
    r_multiple,
    pnl_usd: r_multiple * 50,
    session: 'LONDON',
    htf_open_bias: 'BULLISH',
    entry_time: '2024-01-15T09:30:00Z',
    exit_time: '2024-01-15T11:00:00Z',
    ...overrides,
  }
}

describe('RDistributionChart', () => {
  it('shows empty state when no entries', () => {
    render(<RDistributionChart entries={[]} />)
    expect(screen.getByTestId('r-distribution-empty')).toBeInTheDocument()
  })

  it('shows empty state message text', () => {
    render(<RDistributionChart entries={[]} />)
    expect(screen.getByText('No trade data available')).toBeInTheDocument()
  })

  it('renders chart container when entries are provided', () => {
    const entries = [makeEntry(2.0), makeEntry(-1.0), makeEntry(1.5)]
    render(<RDistributionChart entries={entries} />)
    expect(screen.getByTestId('r-distribution-chart')).toBeInTheDocument()
  })

  it('does not show empty state when entries are provided', () => {
    const entries = [makeEntry(1.0)]
    render(<RDistributionChart entries={entries} />)
    expect(screen.queryByTestId('r-distribution-empty')).not.toBeInTheDocument()
  })

  it('renders chart with mixed positive and negative R entries', () => {
    const entries = [
      makeEntry(2.5),
      makeEntry(-1.0),
      makeEntry(0.5),
      makeEntry(-2.5),
      makeEntry(3.5),
    ]
    render(<RDistributionChart entries={entries} />)
    expect(screen.getByTestId('r-distribution-chart')).toBeInTheDocument()
  })

  it('renders chart with all winning trades', () => {
    const entries = [makeEntry(1.0), makeEntry(2.0), makeEntry(3.0)]
    render(<RDistributionChart entries={entries} />)
    expect(screen.getByTestId('r-distribution-chart')).toBeInTheDocument()
  })

  it('renders chart with all losing trades', () => {
    const entries = [makeEntry(-1.0), makeEntry(-2.0), makeEntry(-0.5)]
    render(<RDistributionChart entries={entries} />)
    expect(screen.getByTestId('r-distribution-chart')).toBeInTheDocument()
  })
})
