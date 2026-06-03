'use client'

import { useAgentStatus } from '@/hooks/useAgentStatus'
import { AgentStatusCard } from '@/components/AgentStatusCard'
import { RiskExposureCard } from '@/components/RiskExposureCard'
import { DecisionLog } from '@/components/DecisionLog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useEffect, useState } from 'react'
import { getDecisionLog } from '@/lib/api'
import type { DecisionLogEntry } from '@/types'

export default function AgentPage() {
  const { status, exposure, loading, error, onPause, onResume } =
    useAgentStatus()
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([])

  useEffect(() => {
    getDecisionLog()
      .then(setDecisions)
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Agent Control</h1>
        <p className="text-sm text-slate-500 mt-1">
          Monitor and control the trading agent
        </p>
      </div>

      {error && (
        <div
          className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
          role="alert"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[0, 1].map((i) => (
            <Card key={i}>
              <CardContent className="h-40 flex items-center justify-center text-slate-400">
                Loading…
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {status && (
            <AgentStatusCard
              status={status}
              onPause={onPause}
              onResume={onResume}
            />
          )}
          {exposure && <RiskExposureCard exposure={exposure} />}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Decision Log</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <DecisionLog entries={decisions} />
        </CardContent>
      </Card>
    </div>
  )
}
