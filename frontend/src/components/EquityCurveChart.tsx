'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { EquityPoint } from '@/types'

interface EquityCurveChartProps {
  data: EquityPoint[]
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
  })
}

export function EquityCurveChart({ data }: EquityCurveChartProps) {
  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-48 text-slate-400 text-sm"
        data-testid="equity-curve-empty"
      >
        No equity data available
      </div>
    )
  }

  return (
    <div data-testid="equity-curve-chart" className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            tick={{ fontSize: 11 }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative P&L']}
            labelFormatter={(label: string) => formatDate(label)}
          />
          <Line
            type="monotone"
            dataKey="cumulative_pnl"
            stroke="#0f172a"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
