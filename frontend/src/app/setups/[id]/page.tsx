import { getSetupById } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatPrice, computeRRatio, formatTimestamp } from '@/lib/utils'
import { ConfidenceBadge } from '@/components/ConfidenceBadge'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

interface SetupDetailPageProps {
  params: Promise<{ id: string }>
}

export default async function SetupDetailPage({ params }: SetupDetailPageProps) {
  const { id } = await params

  let setup
  try {
    setup = await getSetupById(id)
  } catch {
    return (
      <div className="space-y-4">
        <Link
          href="/dashboard"
          className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Dashboard
        </Link>
        <p className="text-red-600">Setup not found or service unavailable.</p>
      </div>
    )
  }

  const {
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
    reasoning,
    time_window,
    narrative_phase,
  } = setup

  const rRatio = computeRRatio(entry_price, sl_price, tp_price)

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Back link */}
      <Link
        href="/dashboard"
        className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Dashboard
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">
            {instrument}
            <span className="ml-2 text-lg font-normal text-slate-500">
              {timeframe}
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">{formatTimestamp(time)}</p>
        </div>
        <ConfidenceBadge score={confidence_score} className="text-base px-3 py-1" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Patterns */}
        <Card>
          <CardHeader>
            <CardTitle>Patterns Detected</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {patterns.map((p) => (
                <Badge key={p} variant="secondary">
                  {p.replace(/_/g, ' ')}
                </Badge>
              ))}
            </div>
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Regime</span>
                <Badge variant="outline">{regime}</Badge>
              </div>
              {time_window && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Time Window</span>
                  <Badge variant="info">{time_window.replace(/_/g, ' ')}</Badge>
                </div>
              )}
              {narrative_phase && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Narrative Phase</span>
                  <span className="font-medium">{narrative_phase}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Confidence */}
        <Card>
          <CardHeader>
            <CardTitle>Confidence Score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-3xl font-bold">
                {Math.round(confidence_score * 100)}%
              </span>
              <ConfidenceBadge score={confidence_score} />
            </div>
            <Progress
              value={confidence_score * 100}
              max={100}
              className="h-3"
            />
            <div className="grid grid-cols-3 gap-2 text-xs text-center mt-2">
              <div className="p-2 rounded bg-orange-50 text-orange-700">
                <p className="font-medium">65%</p>
                <p>Log Only</p>
              </div>
              <div className="p-2 rounded bg-yellow-50 text-yellow-700">
                <p className="font-medium">75%</p>
                <p>Notify</p>
              </div>
              <div className="p-2 rounded bg-green-50 text-green-700">
                <p className="font-medium">85%</p>
                <p>Execute</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* HTF Levels */}
        <Card>
          <CardHeader>
            <CardTitle>HTF Levels ({htf_projections.htf_timeframe})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-slate-500">Open Bias</span>
              <Badge
                variant={
                  htf_projections.open_bias === 'BULLISH'
                    ? 'success'
                    : htf_projections.open_bias === 'BEARISH'
                    ? 'destructive'
                    : 'secondary'
                }
              >
                {htf_projections.open_bias}
              </Badge>
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <p className="text-slate-400 text-xs uppercase">HTF Open</p>
                <p className="font-mono font-medium">
                  {formatPrice(htf_projections.htf_open)}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-xs uppercase">HTF High</p>
                <p className="font-mono font-medium text-green-600">
                  {formatPrice(htf_projections.htf_high)}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-xs uppercase">HTF Low</p>
                <p className="font-mono font-medium text-red-600">
                  {formatPrice(htf_projections.htf_low)}
                </p>
              </div>
            </div>
            <div className="space-y-2 pt-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">High Proximity</span>
                <span className="font-mono">
                  {htf_projections.htf_high_proximity_pct.toFixed(1)}%
                </span>
              </div>
              <Progress value={htf_projections.htf_high_proximity_pct} max={100} />
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">Low Proximity</span>
                <span className="font-mono">
                  {htf_projections.htf_low_proximity_pct.toFixed(1)}%
                </span>
              </div>
              <Progress value={htf_projections.htf_low_proximity_pct} max={100} />
            </div>
          </CardContent>
        </Card>

        {/* Trade Plan */}
        <Card>
          <CardHeader>
            <CardTitle>Trade Plan</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wide">
                  Entry
                </p>
                <p className="font-mono text-lg font-bold">
                  {formatPrice(entry_price)}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wide">
                  R-Ratio
                </p>
                <p className="font-mono text-lg font-bold">{rRatio}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wide">
                  Stop Loss
                </p>
                <p className="font-mono text-lg font-bold text-red-600">
                  {formatPrice(sl_price)}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wide">
                  Take Profit
                </p>
                <p className="font-mono text-lg font-bold text-green-600">
                  {formatPrice(tp_price)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Reasoning */}
      {reasoning && (
        <Card>
          <CardHeader>
            <CardTitle>Trade Reasoning</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
              {reasoning}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
