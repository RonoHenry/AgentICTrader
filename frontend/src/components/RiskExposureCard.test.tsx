import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RiskExposureCard } from './RiskExposureCard'
import type { RiskExposure } from '@/types'

const normalExposure: RiskExposure = {
  daily_dd_pct: 1.0,
  weekly_dd_pct: 2.5,
  open_trades: 1,
  equity: 10000,
}

const warningExposure: RiskExposure = {
  daily_dd_pct: 2.6,
  weekly_dd_pct: 4.0,
  open_trades: 2,
  equity: 9740,
}

describe('RiskExposureCard', () => {
  it('renders daily_dd_pct', () => {
    render(<RiskExposureCard exposure={normalExposure} />)
    expect(screen.getByText('1.00%')).toBeInTheDocument()
  })

  it('renders weekly_dd_pct', () => {
    render(<RiskExposureCard exposure={normalExposure} />)
    expect(screen.getByText('2.50%')).toBeInTheDocument()
  })

  it('renders open_trades', () => {
    render(<RiskExposureCard exposure={normalExposure} />)
    expect(screen.getByTestId('open-trades')).toHaveTextContent('1')
  })

  it('renders equity', () => {
    render(<RiskExposureCard exposure={normalExposure} />)
    expect(screen.getByTestId('equity')).toHaveTextContent('$10,000')
  })

  it('shows warning when daily_dd_pct >= 2.5%', () => {
    render(<RiskExposureCard exposure={warningExposure} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('does not show warning when daily_dd_pct < 2.5%', () => {
    render(<RiskExposureCard exposure={normalExposure} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows warning color on daily DD metric when >= 2.5%', () => {
    render(<RiskExposureCard exposure={warningExposure} />)
    const dailyMetric = screen.getByText('2.60%')
    expect(dailyMetric.className).toMatch(/text-red/)
  })
})
