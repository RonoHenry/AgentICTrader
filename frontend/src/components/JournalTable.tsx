'use client'

import { useRef } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Upload } from 'lucide-react'
import { cn, formatTimestamp } from '@/lib/utils'
import type { TradeJournalEntry } from '@/types'

interface JournalTableProps {
  entries: TradeJournalEntry[]
  onImport?: (file: File) => void
  page?: number
  totalPages?: number
  onPageChange?: (page: number) => void
}

export function JournalTable({
  entries,
  onImport,
  page = 1,
  totalPages = 1,
  onPageChange,
}: JournalTableProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && onImport) {
      onImport(file)
    }
    // Reset so same file can be re-imported
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={handleFileChange}
          aria-label="Import journal file"
          data-testid="file-input"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          data-testid="import-button"
        >
          <Upload className="h-3 w-3 mr-1" aria-hidden="true" />
          Import CSV / XLSX
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Instrument</TableHead>
              <TableHead>Direction</TableHead>
              <TableHead>Entry</TableHead>
              <TableHead>Exit</TableHead>
              <TableHead>R-Multiple</TableHead>
              <TableHead>P&amp;L</TableHead>
              <TableHead>Session</TableHead>
              <TableHead>HTF Bias</TableHead>
              <TableHead>Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className="text-center text-slate-400 py-8"
                >
                  No journal entries found
                </TableCell>
              </TableRow>
            ) : (
              entries.map((entry) => (
                <TableRow key={entry.trade_id} data-testid="journal-row">
                  <TableCell className="font-medium">
                    {entry.instrument}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        entry.direction === 'BUY' ? 'success' : 'destructive'
                      }
                    >
                      {entry.direction}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {entry.entry_price.toFixed(5)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {entry.exit_price.toFixed(5)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'font-mono font-medium',
                      entry.r_multiple > 0
                        ? 'text-green-600'
                        : 'text-red-600'
                    )}
                    data-testid="r-multiple"
                  >
                    {entry.r_multiple > 0 ? '+' : ''}
                    {entry.r_multiple.toFixed(2)}R
                  </TableCell>
                  <TableCell
                    className={cn(
                      'font-mono',
                      entry.pnl_usd > 0 ? 'text-green-600' : 'text-red-600'
                    )}
                  >
                    {entry.pnl_usd > 0 ? '+' : ''}$
                    {entry.pnl_usd.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-xs">{entry.session}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        entry.htf_open_bias === 'BULLISH'
                          ? 'success'
                          : entry.htf_open_bias === 'BEARISH'
                          ? 'destructive'
                          : 'secondary'
                      }
                      className="text-xs"
                    >
                      {entry.htf_open_bias}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-slate-400">
                    {formatTimestamp(entry.entry_time)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange?.(page - 1)}
            disabled={page <= 1}
          >
            Previous
          </Button>
          <span className="text-sm text-slate-600">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange?.(page + 1)}
            disabled={page >= totalPages}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
