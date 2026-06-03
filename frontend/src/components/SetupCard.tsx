'use client'

import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfidenceBadge } from '@/components/ConfidenceBadge'
import { cn, formatPrice, computeRRatio, formatTimestamp } from '@/lib/utils'
import type { Setup } from '@/types'

interface SetupCardProps {
  setup: Setup
  className?: string
}

function getConfidenceBorderColor(score: number): string {
  if (score >= 0.85) return 'border-l-green-500'
  if (score >= 0.75) return 'border-l-yellow-500'
  if (score >= 0.65) return 'border-l-orange-500'
  return 'border-l-gray-300'
}

function getBiasVariant(bias: string): 'success' | 'destructive' | 'secondary' {
  if (bias === 'BULLISH') return 'success'
  if (bias === 'BEARISH') return 'destructive'
  return 'secondary'
}

export function SetupCard({ setup, className }: SetupCardProps) {
  const {
    id,
    instrument,
    timeframe,
    time,
    regime,
    patterns,
    confidence_score,
    htf_projections,
    entry_price,
    sl_price,
    tp_price,
    time_window,
  } = setup

  const rRatio = computeRRatio(entry_price, sl_price, tp_price)
  const borderColor = getConfidenceBorderColor(confidence_score)

  return (
    <Link href={`/setups/${id}`} className="block focus:outline-none focus:ring-2 focus:ring-slate-400 rounded-lg">
      <Card
        className={cn(
          'border-l-4 hover:shadow-md transition-shadow cursor-pointer',
          borderColor,
          className
        )}
        data-testid="setup-card"
      >
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <CardTitle className="text-base font-bold">
              {instrument}
              <span className="ml-2 text-sm font-normal text-slate-500">
                {timeframe}
              </span>
            </CardTitle>
            <ConfidenceBadge score={confidence_score} />
          </div>
          <div className="flex items-center gap-2 flex-wrap mt-1">
            <Badge variant="outline" className="text-xs">
              {regime}
            </Badge>
            <Badge
              variant={getBiasVariant(htf_projections.open_bias)}
              className="text-xs"
              data-testid="htf-bias-badge"
            >
              {htf_projections.open_bias}
            </Badge>
            {time_window && (
              <Badge variant="info" className="text-xs">
                {time_window.replace(/_/g, ' ')}
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="pt-0">
          {/* Patterns */}
          <div className="flex flex-wrap gap-1 mb-3">
            {patterns.map((p) => (
              <Badge key={p} variant="secondary" className="text-xs">
                {p.replace(/_/g, ' ')}
              </Badge>
            ))}
          </div>

          {/* Trade plan */}
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div>
              <p className="text-slate-400 uppercase tracking-wide">Entry</p>
              <p className="font-mono font-medium">{formatPrice(entry_price)}</p>
            </div>
            <div>
              <p className="text-slate-400 uppercase tracking-wide">SL</p>
              <p className="font-mono font-medium text-red-600">
                {formatPrice(sl_price)}
              </p>
            </div>
            <div>
              <p className="text-slate-400 uppercase tracking-wide">TP</p>
              <p className="font-mono font-medium text-green-600">
                {formatPrice(tp_price)}
              </p>
            </div>
            <div>
              <p className="text-slate-400 uppercase tracking-wide">R</p>
              <p className="font-mono font-medium">{rRatio}</p>
            </div>
          </div>

          <p className="text-xs text-slate-400 mt-2">{formatTimestamp(time)}</p>
        </CardContent>
      </Card>
    </Link>
  )
}
