import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`
}

export function formatPrice(value: number | null): string {
  if (value === null) return '—'
  return value.toFixed(5)
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function getConfidenceColor(score: number): string {
  if (score >= 0.85) return 'text-green-600'
  if (score >= 0.75) return 'text-yellow-600'
  if (score >= 0.65) return 'text-orange-500'
  return 'text-gray-400'
}

export function getConfidenceBg(score: number): string {
  if (score >= 0.85) return 'bg-green-100 text-green-800 border-green-200'
  if (score >= 0.75) return 'bg-yellow-100 text-yellow-800 border-yellow-200'
  if (score >= 0.65) return 'bg-orange-100 text-orange-800 border-orange-200'
  return 'bg-gray-100 text-gray-600 border-gray-200'
}

export function computeRRatio(
  entry: number | null,
  sl: number | null,
  tp: number | null
): string {
  if (!entry || !sl || !tp) return '—'
  const risk = Math.abs(entry - sl)
  const reward = Math.abs(tp - entry)
  if (risk === 0) return '—'
  return `${(reward / risk).toFixed(1)}R`
}
