import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EquityCurveChart } from './EquityCurveChart'
import type { EquityPoint } from '@/types'

const sampleData: EquityPoint[] = [
  {
    timestamp: '2024-01-10T10:00:00Z',
    cumulative_pnl: 100,
    trade_id: 'trade-1',
    r_multiple: 2.0,
  },
  {
    timestamp: '2024-01-11T10:00:00Z',
    cumulative_pnl: 250,
    trade_id: 'trade-2',
    r_multiple: 1.5,
  },
  {
    timestamp: '2024-01-12T10:00:00Z',
    cumulative_pnl: 150,
    trade_id: 'trade-3',
    r_multiple: -1.0,
  },
]

describe('EquityCurveChart', () => {
  it('renders without crashing with empty data', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.getByTestId('equity-curve-empty')).toBeInTheDocument()
  })

  it('shows empty state message when no data', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.getByText('No equity data available')).toBeInTheDocument()
  })

  it('renders chart container with sample data', () => {
    render(<EquityCurveChart data={sampleData} />)
    expect(screen.getByTestId('equity-curve-chart')).toBeInTheDocument()
  })

  it('does not show empty state when data is provided', () => {
    render(<EquityCurveChart data={sampleData} />)
    expect(screen.queryByTestId('equity-curve-empty')).not.toBeInTheDocument()
  })
})
