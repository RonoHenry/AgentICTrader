import { describe, it, expect } from 'vitest'
import {
  cn,
  formatCurrency,
  formatPercent,
  formatPrice,
  formatTimestamp,
  getConfidenceColor,
  getConfidenceBg,
  computeRRatio,
} from './utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('handles conditional classes', () => {
    expect(cn('a', false && 'b', 'c')).toBe('a c')
  })

  it('deduplicates tailwind classes (last wins)', () => {
    const result = cn('text-red-500', 'text-blue-500')
    expect(result).toBe('text-blue-500')
  })
})

describe('formatCurrency', () => {
  it('formats positive value as USD', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56')
  })

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats negative value', () => {
    expect(formatCurrency(-500)).toBe('-$500.00')
  })
})

describe('formatPercent', () => {
  it('converts 0.65 to 65.00%', () => {
    expect(formatPercent(0.65)).toBe('65.00%')
  })

  it('respects custom decimal places', () => {
    expect(formatPercent(0.6543, 1)).toBe('65.4%')
  })

  it('handles 0', () => {
    expect(formatPercent(0)).toBe('0.00%')
  })

  it('handles 1.0', () => {
    expect(formatPercent(1.0)).toBe('100.00%')
  })
})

describe('formatPrice', () => {
  it('formats price to 5 decimal places', () => {
    expect(formatPrice(1.085)).toBe('1.08500')
  })

  it('returns em dash for null', () => {
    expect(formatPrice(null)).toBe('—')
  })

  it('formats zero', () => {
    expect(formatPrice(0)).toBe('0.00000')
  })
})

describe('formatTimestamp', () => {
  it('returns a non-empty string for a valid ISO timestamp', () => {
    const result = formatTimestamp('2024-01-15T09:30:00Z')
    expect(result).toBeTruthy()
    expect(typeof result).toBe('string')
  })
})

describe('getConfidenceColor', () => {
  it('returns green for score >= 0.85', () => {
    expect(getConfidenceColor(0.85)).toMatch(/green/)
    expect(getConfidenceColor(0.90)).toMatch(/green/)
  })

  it('returns yellow for score 0.75–0.84', () => {
    expect(getConfidenceColor(0.75)).toMatch(/yellow/)
    expect(getConfidenceColor(0.80)).toMatch(/yellow/)
  })

  it('returns orange for score 0.65–0.74', () => {
    expect(getConfidenceColor(0.65)).toMatch(/orange/)
    expect(getConfidenceColor(0.70)).toMatch(/orange/)
  })

  it('returns gray for score below 0.65', () => {
    expect(getConfidenceColor(0.50)).toMatch(/gray/)
  })
})

describe('getConfidenceBg', () => {
  it('returns green bg for score >= 0.85', () => {
    expect(getConfidenceBg(0.85)).toMatch(/green/)
  })

  it('returns yellow bg for score 0.75–0.84', () => {
    expect(getConfidenceBg(0.78)).toMatch(/yellow/)
  })

  it('returns orange bg for score 0.65–0.74', () => {
    expect(getConfidenceBg(0.68)).toMatch(/orange/)
  })

  it('returns gray bg for score below 0.65', () => {
    expect(getConfidenceBg(0.50)).toMatch(/gray/)
  })
})

describe('computeRRatio', () => {
  it('computes correct R ratio for a 2R trade', () => {
    // entry=1.085, sl=1.083 (risk=0.002), tp=1.089 (reward=0.004) → 2R
    expect(computeRRatio(1.085, 1.083, 1.089)).toBe('2.0R')
  })

  it('returns em dash when entry is null', () => {
    expect(computeRRatio(null, 1.083, 1.089)).toBe('—')
  })

  it('returns em dash when sl is null', () => {
    expect(computeRRatio(1.085, null, 1.089)).toBe('—')
  })

  it('returns em dash when tp is null', () => {
    expect(computeRRatio(1.085, 1.083, null)).toBe('—')
  })

  it('returns em dash when risk is zero (entry == sl)', () => {
    expect(computeRRatio(1.085, 1.085, 1.089)).toBe('—')
  })

  it('handles bearish trade (entry > tp)', () => {
    // entry=1.085, sl=1.087 (risk=0.002), tp=1.081 (reward=0.004) → 2R
    expect(computeRRatio(1.085, 1.087, 1.081)).toBe('2.0R')
  })
})
