'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { TradeJournalEntry } from '@/types'

interface RDistributionChartProps {
  entries: TradeJournalEntry[]
}

interface BucketData {
  bucket: string
  count: number
  isPositive: boolean
}

function buildBuckets(entries: TradeJournalEntry[]): BucketData[] {
  if (entries.length === 0) return []

  // Fixed buckets: < -2R, -2 to -1, -1 to 0, 0 to 1, 1 to 2, 2 to 3, > 3R
  const buckets: { label: string; min: number; max: number }[] = [
    { label: '< -2R', min: -Infinity, max: -2 },
    { label: '-2 to -1R', min: -2, max: -1 },
    { label: '-1 to 0R', min: -1, max: 0 },
    { label: '0 to 1R', min: 0, max: 1 },
    { label: '1 to 2R', min: 1, max: 2 },
    { label: '2 to 3R', min: 2, max: 3 },
    { label: '> 3R', min: 3, max: Infinity },
  ]

  return buckets.map(({ label, min, max }) => ({
    bucket: label,
    count: entries.filter((e) => e.r_multiple >= min && e.r_multiple < max)
      .length,
    isPositive: min >= 0,
  }))
}

export function RDistributionChart({ entries }: RDistributionChartProps) {
  if (entries.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-48 text-slate-400 text-sm"
        data-testid="r-distribution-empty"
      >
        No trade data available
      </div>
    )
  }

  const data = buildBuckets(entries)

  return (
    <div data-testid="r-distribution-chart" className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="bucket"
            tick={{ fontSize: 10 }}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            label={{
              value: 'Trades',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 11, fill: '#94a3b8' },
            }}
          />
          <Tooltip
            formatter={(value: number) => [value, 'Trades']}
            labelFormatter={(label: string) => `R-Multiple: ${label}`}
          />
          <ReferenceLine x="0 to 1R" stroke="#94a3b8" strokeDasharray="3 3" />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.isPositive ? '#16a34a' : '#dc2626'}
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
