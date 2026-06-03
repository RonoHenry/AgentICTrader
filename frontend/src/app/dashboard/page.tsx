'use client'

import { useSetupsFeed } from '@/hooks/useSetupsFeed'
import { SetupCard } from '@/components/SetupCard'
import { Badge } from '@/components/ui/badge'
import { Wifi, WifiOff, RefreshCw } from 'lucide-react'

export default function DashboardPage() {
  const { setups, connected, error } = useSetupsFeed()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Live Setups</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time setup feed — {setups.length} active
          </p>
        </div>
        <div className="flex items-center gap-2">
          {connected ? (
            <Badge variant="success" className="flex items-center gap-1">
              <Wifi className="h-3 w-3" aria-hidden="true" />
              Live
            </Badge>
          ) : (
            <Badge variant="secondary" className="flex items-center gap-1">
              <WifiOff className="h-3 w-3" aria-hidden="true" />
              Polling
            </Badge>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="flex items-center gap-2 p-3 bg-orange-50 border border-orange-200 rounded-md text-sm text-orange-700"
          role="alert"
        >
          <RefreshCw className="h-4 w-4 shrink-0" aria-hidden="true" />
          WebSocket unavailable — falling back to polling every 10s
        </div>
      )}

      {/* Setups grid */}
      {setups.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-slate-400">
          <RefreshCw className="h-8 w-8 mb-3 animate-spin" aria-hidden="true" />
          <p className="text-sm">Waiting for setups…</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {setups.map((setup) => (
            <SetupCard key={setup.id} setup={setup} />
          ))}
        </div>
      )}
    </div>
  )
}
