'use client'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { formatTimestamp } from '@/lib/utils'
import type { DecisionLogEntry } from '@/types'

interface DecisionLogProps {
  entries: DecisionLogEntry[]
}

function getDecisionVariant(
  decision: DecisionLogEntry['decision']
): 'success' | 'warning' | 'secondary' {
  if (decision === 'TAKEN') return 'success'
  if (decision === 'NOTIFIED') return 'warning'
  return 'secondary'
}

export function DecisionLog({ entries }: DecisionLogProps) {
  return (
    <div className="rounded-md border" data-testid="decision-log">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Instrument</TableHead>
            <TableHead>Decision</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Regime</TableHead>
            <TableHead>Reasoning</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={6}
                className="text-center text-slate-400 py-8"
              >
                No decisions logged yet
              </TableCell>
            </TableRow>
          ) : (
            entries.map((entry) => (
              <TableRow key={entry.id} data-testid="decision-row">
                <TableCell className="text-xs text-slate-400 whitespace-nowrap">
                  {formatTimestamp(entry.timestamp)}
                </TableCell>
                <TableCell className="font-medium">{entry.instrument}</TableCell>
                <TableCell>
                  <Badge
                    variant={getDecisionVariant(entry.decision)}
                    data-testid={`decision-badge-${entry.decision.toLowerCase()}`}
                  >
                    {entry.decision}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {Math.round(entry.confidence * 100)}%
                </TableCell>
                <TableCell className="text-xs">{entry.regime}</TableCell>
                <TableCell className="text-xs text-slate-600 max-w-xs truncate">
                  {entry.reasoning}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
