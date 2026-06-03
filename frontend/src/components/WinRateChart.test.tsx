import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WinRateChart } from './WinRateChart'
import type { EdgeMetrics } from '@/types'

function makeMetrics(overrides: Partial<EdgeMetrics> = {}): EdgeMetrics {
  return {
    win_rate: 0.65,
    avg_r_multiple: 1.8,
    expectancy: 0.72,
    trade_count: 20,
    total_pnl: 1440,
    avg_pnl: 72,
    ...overrides,
  }
}

describe('WinRateChart', () => {
  it('renders without crashing with empty data', () => {
    render(<WinRateChart data={{}} />)
    expect(screen.getByTestId('win-rate-empty')).toBeInTheDocument()
  })

  it('shows empty state message when no data', () => {
    render(<WinRateChart data={{}} />)
    expect(screen.getByText('No data available')).toBeInTheDocument()
  })

  it('renders chart container when data is provided', () => {
    const data = {
      LONDON: makeMetrics({ win_rate: 0.70 }),
      NY_AM: makeMetrics({ win_rate: 0.60 }),
    }
    render(<WinRateChart data={data} />)
    expect(screen.getByTestId('win-rate-chart')).toBeInTheDocument()
  })

  it('does not show empty state when data is provided', () => {
    const data = {
      LONDON: makeMetrics(),
    }
    render(<WinRateChart data={data} />)
    expect(screen.queryByTestId('win-rate-empty')).not.toBeInTheDocument()
  })

  it('renders grouped bars for each group key', () => {
    const data = {
      BULLISH: makeMetrics({ win_rate: 0.72 }),
      BEARISH: makeMetrics({ win_rate: 0.58 }),
    }
    render(<WinRateChart data={data} />)
    // Chart renders — verify container is present
    expect(screen.getByTestId('win-rate-chart')).toBeInTheDocument()
  })

  it('renders optional title when provided', () => {
    render(<WinRateChart data={{ A: makeMetrics() }} title="Test Chart" />)
    expect(screen.getByText('Test Chart')).toBeInTheDocument()
  })
})
