import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfidenceBadge } from './ConfidenceBadge'

describe('ConfidenceBadge', () => {
  it('displays score as percentage', () => {
    render(<ConfidenceBadge score={0.87} />)
    expect(screen.getByText('87%')).toBeInTheDocument()
  })

  it('renders green (success) variant for score >= 0.85', () => {
    const { container } = render(<ConfidenceBadge score={0.85} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/bg-green/)
  })

  it('renders yellow (warning) variant for score 0.75–0.84', () => {
    const { container } = render(<ConfidenceBadge score={0.80} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/bg-yellow/)
  })

  it('renders orange (danger) variant for score 0.65–0.74', () => {
    const { container } = render(<ConfidenceBadge score={0.70} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/bg-orange/)
  })

  it('renders secondary variant for score below 0.65', () => {
    const { container } = render(<ConfidenceBadge score={0.50} />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/bg-slate/)
  })

  it('rounds score to nearest integer percentage', () => {
    render(<ConfidenceBadge score={0.756} />)
    expect(screen.getByText('76%')).toBeInTheDocument()
  })

  it('renders 100% for score of 1.0', () => {
    render(<ConfidenceBadge score={1.0} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })

  it('renders 0% for score of 0.0', () => {
    render(<ConfidenceBadge score={0.0} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })
})
