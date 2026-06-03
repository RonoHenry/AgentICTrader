'use client'

import { useCallback, useEffect, useState } from 'react'
import { JournalTable } from '@/components/JournalTable'
import { getTradeJournal, importJournalFile } from '@/lib/api'
import type { TradeJournalEntry } from '@/types'

const PAGE_SIZE = 50

export default function JournalPage() {
  const [entries, setEntries] = useState<TradeJournalEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [importMsg, setImportMsg] = useState<string | null>(null)

  const fetchPage = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const data = await getTradeJournal(p, PAGE_SIZE)
      setEntries(data.entries)
      setTotal(data.total)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load journal')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPage(page)
  }, [fetchPage, page])

  const handleImport = async (file: File) => {
    try {
      const result = await importJournalFile(file)
      setImportMsg(`Imported ${result.imported} trades successfully`)
      fetchPage(1)
    } catch (err) {
      setImportMsg(
        err instanceof Error ? err.message : 'Import failed'
      )
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Trade Journal</h1>
        <p className="text-sm text-slate-500 mt-1">
          {total} total trades
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

      {importMsg && (
        <div
          className="p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-700"
          role="status"
        >
          {importMsg}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-400">
          Loading journal…
        </div>
      ) : (
        <JournalTable
          entries={entries}
          onImport={handleImport}
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
        />
      )}
    </div>
  )
}
