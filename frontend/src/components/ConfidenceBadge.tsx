'use client'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface ConfidenceBadgeProps {
  score: number
  className?: string
}

export function ConfidenceBadge({ score, className }: ConfidenceBadgeProps) {
  const pct = Math.round(score * 100)

  let variant: 'success' | 'warning' | 'danger' | 'secondary'
  let label: string

  if (score >= 0.85) {
    variant = 'success'
    label = 'High'
  } else if (score >= 0.75) {
    variant = 'warning'
    label = 'Medium'
  } else if (score >= 0.65) {
    variant = 'danger'
    label = 'Low'
  } else {
    variant = 'secondary'
    label = 'Below Floor'
  }

  return (
    <Badge
      variant={variant}
      className={cn('font-mono tabular-nums', className)}
      aria-label={`Confidence: ${pct}% (${label})`}
    >
      {pct}%
    </Badge>
  )
}
