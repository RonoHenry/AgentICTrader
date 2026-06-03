'use client'

import { useCallback, useEffect, useState } from 'react'
import type { AgentStatus, RiskExposure } from '@/types'
import { getAgentStatus, getRiskExposure, pauseAgent, resumeAgent } from '@/lib/api'

const POLL_INTERVAL_MS = 5_000

export function useAgentStatus(userId = 'default') {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [exposure, setExposure] = useState<RiskExposure | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([
        getAgentStatus(),
        getRiskExposure(userId),
      ])
      setStatus(s)
      setExposure(e)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agent status')
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    fetchAll()
    const timer = setInterval(fetchAll, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [fetchAll])

  const handlePause = useCallback(async () => {
    await pauseAgent()
    await fetchAll()
  }, [fetchAll])

  const handleResume = useCallback(async () => {
    await resumeAgent()
    await fetchAll()
  }, [fetchAll])

  return { status, exposure, loading, error, onPause: handlePause, onResume: handleResume }
}
