'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { EdgeMetrics } from '@/types'

interface WinRateChartProps {
  data: Record<string, EdgeMetrics>
  title?: string
}

export function WinRateChart({ data, title }: WinRateChartProps) {
  const chartData = Object.entries(data).map(([key, metrics]) => ({
    group: key,
    win_rate: parseFloat((metrics.win_rate * 100).toFixed(1)),
    avg_r: parseFloat(metrics.avg_r_multiple.toFixed(2)),
    trade_count: metrics.trade_count,
  }))

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-48 text-slate-400 text-sm"
        data-testid="win-rate-empty"
      >
        No data available
      </div>
    )
  }

  return (
    <div data-testid="win-rate-chart" className="w-full h-64">
      {title && (
        <p className="text-sm font-medium text-slate-700 mb-2">{title}</p>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="group" tick={{ fontSize: 11 }} tickLine={false} />
          <YAxis
            yAxisId="left"
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(v: number) => `${v}R`}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              if (name === 'win_rate') return [`${value}%`, 'Win Rate']
              if (name === 'avg_r') return [`${value}R`, 'Avg R']
              return [value, name]
            }}
          />
          <Legend />
          <Bar
            yAxisId="left"
            dataKey="win_rate"
            name="Win Rate"
            fill="#0f172a"
            radius={[2, 2, 0, 0]}
          />
          <Bar
            yAxisId="right"
            dataKey="avg_r"
            name="Avg R"
            fill="#64748b"
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
