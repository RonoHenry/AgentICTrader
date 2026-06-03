import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SetupCard } from './SetupCard'
import type { Setup } from '@/types'

function makeSetup(overrides: Partial<Setup> = {}): Setup {
  return {
    id: 'test-1',
    instrument: 'EURUSD',
    timeframe: 'M15',
    time: '2024-01-15T09:30:00Z',
    regime: 'TRENDING_BULLISH',
    patterns: ['BOS_CONFIRMED', 'FVG_PRESENT'],
    confidence_score: 0.87,
    htf_projections: {
      htf_timeframe: 'H1',
      htf_open: 1.08500,
      htf_high: 1.09000,
      htf_low: 1.08000,
      open_bias: 'BULLISH',
      htf_high_proximity_pct: 40,
      htf_low_proximity_pct: 60,
      htf_body_pct: 50,
      htf_upper_wick_pct: 25,
      htf_lower_wick_pct: 25,
      htf_close_position: 0.7,
    },
    entry_price: 1.08600,
    sl_price: 1.08400,
    tp_price: 1.09000,
    time_window: 'NY_AM_KILLZONE',
    ...overrides,
  }
}

describe('SetupCard', () => {
  it('renders instrument name', () => {
    render(<SetupCard setup={makeSetup()} />)
    expect(screen.getByText('EURUSD')).toBeInTheDocument()
  })

  it('renders timeframe', () => {
    render(<SetupCard setup={makeSetup()} />)
    expect(screen.getByText('M15')).toBeInTheDocument()
  })

  it('shows confidence score as percentage', () => {
    render(<SetupCard setup={makeSetup({ confidence_score: 0.87 })} />)
    expect(screen.getByText('87%')).toBeInTheDocument()
  })

  it('applies green styling when confidence >= 0.85', () => {
    render(<SetupCard setup={makeSetup({ confidence_score: 0.90 })} />)
    const card = screen.getByTestId('setup-card')
    expect(card.className).toMatch(/border-l-green/)
  })

  it('applies yellow styling when confidence is 0.75–0.84', () => {
    render(<SetupCard setup={makeSetup({ confidence_score: 0.78 })} />)
    const card = screen.getByTestId('setup-card')
    expect(card.className).toMatch(/border-l-yellow/)
  })

  it('applies orange styling when confidence is 0.65–0.74', () => {
    render(<SetupCard setup={makeSetup({ confidence_score: 0.68 })} />)
    const card = screen.getByTestId('setup-card')
    expect(card.className).toMatch(/border-l-orange/)
  })

  it('shows HTF open bias badge', () => {
    render(<SetupCard setup={makeSetup()} />)
    expect(screen.getByTestId('htf-bias-badge')).toHaveTextContent('BULLISH')
  })

  it('shows BEARISH bias badge', () => {
    render(
      <SetupCard
        setup={makeSetup({
          htf_projections: {
            ...makeSetup().htf_projections,
            open_bias: 'BEARISH',
          },
        })}
      />
    )
    expect(screen.getByTestId('htf-bias-badge')).toHaveTextContent('BEARISH')
  })

  it('renders patterns as badges', () => {
    render(<SetupCard setup={makeSetup()} />)
    expect(screen.getByText('BOS CONFIRMED')).toBeInTheDocument()
    expect(screen.getByText('FVG PRESENT')).toBeInTheDocument()
  })

  it('renders entry, SL, TP prices', () => {
    render(<SetupCard setup={makeSetup()} />)
    expect(screen.getByText('1.08600')).toBeInTheDocument()
    expect(screen.getByText('1.08400')).toBeInTheDocument()
    expect(screen.getByText('1.09000')).toBeInTheDocument()
  })

  it('shows dash for null entry price', () => {
    render(<SetupCard setup={makeSetup({ entry_price: null })} />)
    // Should show em dash for null values
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })
})
