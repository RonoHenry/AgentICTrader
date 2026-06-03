import type {
  Setup,
  AgentStatus,
  RiskExposure,
  EdgeMetrics,
  EquityPoint,
  TradeJournalEntry,
  DecisionLogEntry,
} from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const ANALYTICS_URL =
  process.env.NEXT_PUBLIC_ANALYTICS_URL ?? 'http://localhost:8002'
const RISK_URL = process.env.NEXT_PUBLIC_RISK_URL ?? 'http://localhost:8003'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: 'no-store', ...options })
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

// ── Agent / Risk Engine ──────────────────────────────────────────────────────

export async function getAgentStatus(): Promise<AgentStatus> {
  return fetchJSON<AgentStatus>(`${API_URL}/status`)
}

export async function pauseAgent(): Promise<void> {
  await fetchJSON<unknown>(`${API_URL}/agent/pause`, { method: 'POST' })
}

export async function resumeAgent(): Promise<void> {
  await fetchJSON<unknown>(`${API_URL}/agent/resume`, { method: 'POST' })
}

export async function getRiskExposure(userId = 'default'): Promise<RiskExposure> {
  return fetchJSON<RiskExposure>(`${RISK_URL}/exposure?user_id=${userId}`)
}

// ── Setups ───────────────────────────────────────────────────────────────────

export async function getSetups(): Promise<Setup[]> {
  return fetchJSON<Setup[]>(`${API_URL}/setups`)
}

export async function getSetupById(id: string): Promise<Setup> {
  return fetchJSON<Setup>(`${API_URL}/setups/${id}`)
}

// ── Decision Log ─────────────────────────────────────────────────────────────

export async function getDecisionLog(): Promise<DecisionLogEntry[]> {
  return fetchJSON<DecisionLogEntry[]>(`${API_URL}/agent/decisions`)
}

// ── Analytics ────────────────────────────────────────────────────────────────

export async function getAnalyticsSummary(): Promise<EdgeMetrics> {
  return fetchJSON<EdgeMetrics>(`${ANALYTICS_URL}/analytics/summary`)
}

export async function getEdgeByGroup(
  groupBy: 'session' | 'instrument' | 'htf_open_bias'
): Promise<Record<string, EdgeMetrics>> {
  return fetchJSON<Record<string, EdgeMetrics>>(
    `${ANALYTICS_URL}/analytics/edge?group_by=${groupBy}`
  )
}

export async function getEquityCurve(): Promise<EquityPoint[]> {
  return fetchJSON<EquityPoint[]>(`${ANALYTICS_URL}/analytics/equity-curve`)
}

// ── Trade Journal ─────────────────────────────────────────────────────────────

export async function getTradeJournal(
  page = 1,
  pageSize = 50
): Promise<{ entries: TradeJournalEntry[]; total: number }> {
  return fetchJSON<{ entries: TradeJournalEntry[]; total: number }>(
    `${ANALYTICS_URL}/analytics/journal?page=${page}&page_size=${pageSize}`
  )
}

export async function importJournalFile(file: File): Promise<{ imported: number }> {
  const formData = new FormData()
  formData.append('file', file)
  return fetchJSON<{ imported: number }>(`${ANALYTICS_URL}/analytics/import`, {
    method: 'POST',
    body: formData,
  })
}
