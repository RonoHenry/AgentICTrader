'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Activity, AlertTriangle, Pause, Play } from 'lucide-react'
import type { AgentStatus } from '@/types'

interface AgentStatusCardProps {
  status: AgentStatus
  onPause: () => void
  onResume: () => void
  loading?: boolean
}

export function AgentStatusCard({
  status,
  onPause,
  onResume,
  loading = false,
}: AgentStatusCardProps) {
  const { healthy, kill_switch_active } = status

  return (
    <Card data-testid="agent-status-card">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          {healthy ? (
            <Activity className="h-4 w-4 text-green-500" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-red-500" aria-hidden="true" />
          )}
          Agent Status
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">Health</span>
          <Badge
            variant={healthy ? 'success' : 'destructive'}
            data-testid="health-badge"
          >
            {healthy ? 'Healthy' : 'Unhealthy'}
          </Badge>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">Kill Switch</span>
          <Badge
            variant={kill_switch_active ? 'destructive' : 'secondary'}
            data-testid="kill-switch-badge"
          >
            {kill_switch_active ? 'ACTIVE' : 'Inactive'}
          </Badge>
        </div>

        <div className="flex gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onPause}
            disabled={loading || kill_switch_active}
            aria-label="Pause agent"
            data-testid="pause-button"
          >
            <Pause className="h-3 w-3 mr-1" aria-hidden="true" />
            Pause
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={onResume}
            disabled={loading || !kill_switch_active}
            aria-label="Resume agent"
            data-testid="resume-button"
          >
            <Play className="h-3 w-3 mr-1" aria-hidden="true" />
            Resume
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
