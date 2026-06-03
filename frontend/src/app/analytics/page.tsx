'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EquityCurveChart } from '@/components/EquityCurveChart'
import { WinRateChart } from '@/components/WinRateChart'
import { RDistributionChart } from '@/components/RDistributionChart'
import {
  getAnalyticsSummary,
  getEdgeByGroup,
  getEquityCurve,
  getTradeJournal,
} from '@/lib/api'
import type { EdgeMetrics, EquityPoint, TradeJournalEntry } from '@/types'
import { formatPercent } from '@/lib/utils'

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<EdgeMetrics | null>(null)
  const [bySession, setBySession] = useState<Record<string, EdgeMetrics>>({})
  const [byInstrument, setByInstrument] = useState<Record<string, EdgeMetrics>>({})
  const [byBias, setByBias] = useState<Record<string, EdgeMetrics>>({})
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([])
  const [journalEntries, setJournalEntries] = useState<TradeJournalEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      getAnalyticsSummary(),
      getEdgeByGroup('session'),
      getEdgeByGroup('instrument'),
      getEdgeByGroup('htf_open_bias'),
      getEquityCurve(),
      getTradeJournal(1, 500),
    ])
      .then(([sum, sess, inst, bias, equity, journal]) => {
        setSummary(sum)
        setBySession(sess)
        setByInstrument(inst)
        setByBias(bias)
        setEquityCurve(equity)
        setJournalEntries(journal.entries)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load analytics')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400">
        Loading analytics…
      </div>
    )
  }

  if (error) {
    return (
      <div
        className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
        role="alert"
      >
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
        <p className="text-sm text-slate-500 mt-1">
          Edge analysis and performance metrics
        </p>
      </div>

      {/* Summary KPIs */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[
            { label: 'Win Rate', value: formatPercent(summary.win_rate) },
            { label: 'Avg R', value: `${summary.avg_r_multiple.toFixed(2)}R` },
            { label: 'Expectancy', value: `${summary.expectancy.toFixed(2)}R` },
            { label: 'Trades', value: summary.trade_count.toString() },
            {
              label: 'Total P&L',
              value: `$${summary.total_pnl.toFixed(0)}`,
            },
            { label: 'Avg P&L', value: `$${summary.avg_pnl.toFixed(2)}` },
          ].map(({ label, value }) => (
            <Card key={label}>
              <CardContent className="pt-4 pb-4">
                <p className="text-xs text-slate-400 uppercase tracking-wide">
                  {label}
                </p>
                <p className="text-xl font-bold mt-1">{value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Equity Curve */}
      <Card>
        <CardHeader>
          <CardTitle>Equity Curve</CardTitle>
        </CardHeader>
        <CardContent>
          <EquityCurveChart data={equityCurve} />
        </CardContent>
      </Card>

      {/* R-Multiple Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>R-Multiple Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <RDistributionChart entries={journalEntries} />
        </CardContent>
      </Card>

      {/* Win Rate by Session */}
      <Card>
        <CardHeader>
          <CardTitle>Win Rate by Session</CardTitle>
        </CardHeader>
        <CardContent>
          <WinRateChart data={bySession} />
        </CardContent>
      </Card>

      {/* Win Rate by Instrument */}
      <Card>
        <CardHeader>
          <CardTitle>Win Rate by Instrument</CardTitle>
        </CardHeader>
        <CardContent>
          <WinRateChart data={byInstrument} />
        </CardContent>
      </Card>

      {/* HTF Bias Performance */}
      <Card>
        <CardHeader>
          <CardTitle>HTF Bias Performance</CardTitle>
        </CardHeader>
        <CardContent>
          <WinRateChart data={byBias} title="BULLISH vs BEARISH win rates" />
        </CardContent>
      </Card>
    </div>
  )
}
