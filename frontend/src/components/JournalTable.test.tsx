import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JournalTable } from './JournalTable'
import type { TradeJournalEntry } from '@/types'

function makeEntry(overrides: Partial<TradeJournalEntry> = {}): TradeJournalEntry {
  return {
    trade_id: 'trade-1',
    instrument: 'EURUSD',
    direction: 'BUY',
    entry_price: 1.08500,
    exit_price: 1.09000,
    r_multiple: 2.5,
    pnl_usd: 125.0,
    session: 'LONDON',
    htf_open_bias: 'BULLISH',
    entry_time: '2024-01-15T09:30:00Z',
    exit_time: '2024-01-15T11:00:00Z',
    ...overrides,
  }
}

describe('JournalTable', () => {
  it('renders table rows for each trade entry', () => {
    const entries = [
      makeEntry({ trade_id: 'trade-1' }),
      makeEntry({ trade_id: 'trade-2', instrument: 'GBPUSD' }),
    ]
    render(<JournalTable entries={entries} />)
    const rows = screen.getAllByTestId('journal-row')
    expect(rows).toHaveLength(2)
  })

  it('shows correct R-multiple values', () => {
    const entries = [makeEntry({ r_multiple: 2.5 })]
    render(<JournalTable entries={entries} />)
    expect(screen.getByTestId('r-multiple')).toHaveTextContent('+2.50R')
  })

  it('shows negative R-multiple without plus sign', () => {
    const entries = [makeEntry({ r_multiple: -1.0 })]
    render(<JournalTable entries={entries} />)
    expect(screen.getByTestId('r-multiple')).toHaveTextContent('-1.00R')
  })

  it('import button is present', () => {
    render(<JournalTable entries={[]} />)
    expect(screen.getByTestId('import-button')).toBeInTheDocument()
  })

  it('shows empty state when no entries', () => {
    render(<JournalTable entries={[]} />)
    expect(screen.getByText('No journal entries found')).toBeInTheDocument()
  })

  it('renders instrument names', () => {
    const entries = [
      makeEntry({ trade_id: 'trade-1', instrument: 'EURUSD' }),
      makeEntry({ trade_id: 'trade-2', instrument: 'XAUUSD' }),
    ]
    render(<JournalTable entries={entries} />)
    expect(screen.getByText('EURUSD')).toBeInTheDocument()
    expect(screen.getByText('XAUUSD')).toBeInTheDocument()
  })

  it('calls onImport when file is selected', async () => {
    const onImport = vi.fn()
    render(<JournalTable entries={[]} onImport={onImport} />)

    const fileInput = screen.getByTestId('file-input')
    const file = new File(['col1,col2\nval1,val2'], 'trades.csv', {
      type: 'text/csv',
    })

    await userEvent.upload(fileInput, file)
    expect(onImport).toHaveBeenCalledWith(file)
  })
})
