'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { RiskExposure } from '@/types'

interface RiskExposureCardProps {
  exposure: RiskExposure
}

const DAILY_DD_WARNING_THRESHOLD = 2.5
const DAILY_DD_MAX = 3.0
const WEEKLY_DD_MAX = 6.0

function MetricRow({
  label,
  value,
  max,
  warn,
  unit = '%',
}: {
  label: string
  value: number
  max: number
  warn: boolean
  unit?: string
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span
          className={cn(
            'font-mono font-medium',
            warn ? 'text-red-600' : 'text-slate-900'
          )}
          data-testid={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
        >
          {value.toFixed(2)}{unit}
        </span>
      </div>
      <Progress
        value={value}
        max={max}
        className={cn(warn ? '[&>div]:bg-red-500' : '[&>div]:bg-slate-700')}
      />
    </div>
  )
}

export function RiskExposureCard({ exposure }: RiskExposureCardProps) {
  const { daily_dd_pct, weekly_dd_pct, open_trades, equity } = exposure
  const dailyWarn = daily_dd_pct >= DAILY_DD_WARNING_THRESHOLD

  return (
    <Card data-testid="risk-exposure-card">
      <CardHeader className="pb-2">
        <CardTitle>Risk Exposure</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <MetricRow
          label="Daily DD"
          value={daily_dd_pct}
          max={DAILY_DD_MAX}
          warn={dailyWarn}
        />
        <MetricRow
          label="Weekly DD"
          value={weekly_dd_pct}
          max={WEEKLY_DD_MAX}
          warn={weekly_dd_pct >= WEEKLY_DD_MAX * 0.8}
        />

        <div className="grid grid-cols-2 gap-4 pt-2">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wide">
              Open Trades
            </p>
            <p
              className="text-2xl font-bold"
              data-testid="open-trades"
            >
              {open_trades}
              <span className="text-sm font-normal text-slate-400">/3</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wide">
              Equity
            </p>
            <p
              className="text-2xl font-bold"
              data-testid="equity"
            >
              ${equity.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </p>
          </div>
        </div>

        {dailyWarn && (
          <p className="text-xs text-red-600 font-medium" role="alert">
            ⚠ Daily drawdown approaching limit ({DAILY_DD_MAX}%)
          </p>
        )}
      </CardContent>
    </Card>
  )
}
