import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DecisionLog } from './DecisionLog'
import type { DecisionLogEntry } from '@/types'

function makeEntry(overrides: Partial<DecisionLogEntry> = {}): DecisionLogEntry {
  return {
    id: 'dec-1',
    timestamp: '2024-01-15T09:30:00Z',
    instrument: 'EURUSD',
    decision: 'TAKEN',
    confidence: 0.88,
    reasoning: 'Strong bullish setup at discount',
    regime: 'TRENDING_BULLISH',
    patterns: ['BOS_CONFIRMED'],
    ...overrides,
  }
}

describe('DecisionLog', () => {
  it('renders decision entries', () => {
    const entries = [
      makeEntry({ id: 'dec-1' }),
      makeEntry({ id: 'dec-2', instrument: 'GBPUSD' }),
    ]
    render(<DecisionLog entries={entries} />)
    const rows = screen.getAllByTestId('decision-row')
    expect(rows).toHaveLength(2)
  })

  it('shows TAKEN badge', () => {
    render(<DecisionLog entries={[makeEntry({ decision: 'TAKEN' })]} />)
    expect(screen.getByTestId('decision-badge-taken')).toHaveTextContent('TAKEN')
  })

  it('shows SKIPPED badge', () => {
    render(<DecisionLog entries={[makeEntry({ decision: 'SKIPPED' })]} />)
    expect(screen.getByTestId('decision-badge-skipped')).toHaveTextContent('SKIPPED')
  })

  it('shows NOTIFIED badge', () => {
    render(<DecisionLog entries={[makeEntry({ decision: 'NOTIFIED' })]} />)
    expect(screen.getByTestId('decision-badge-notified')).toHaveTextContent('NOTIFIED')
  })

  it('shows empty state when no entries', () => {
    render(<DecisionLog entries={[]} />)
    expect(screen.getByText('No decisions logged yet')).toBeInTheDocument()
  })

  it('renders instrument names', () => {
    render(<DecisionLog entries={[makeEntry({ instrument: 'XAUUSD' })]} />)
    expect(screen.getByText('XAUUSD')).toBeInTheDocument()
  })

  it('renders confidence as percentage', () => {
    render(<DecisionLog entries={[makeEntry({ confidence: 0.88 })]} />)
    expect(screen.getByText('88%')).toBeInTheDocument()
  })

  it('renders reasoning text', () => {
    render(
      <DecisionLog
        entries={[makeEntry({ reasoning: 'Strong bullish setup at discount' })]}
      />
    )
    expect(
      screen.getByText('Strong bullish setup at discount')
    ).toBeInTheDocument()
  })
})
