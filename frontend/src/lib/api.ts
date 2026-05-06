/**
 * REST API client for Aurora Flux backend.
 * All endpoints return typed responses.
 */

import type {
  SystemStatus,
  Position,
  Trade,
  Signal,
  Strategy,
  EvolutionEvent,
  GovernanceDecision,
  RiskSummary,
  RegimeClassification,
  AuditEntry,
  AuditVerification,
  PerformanceSummary,
  EquityPoint,
  ChatMessage,
  AccountInfo,
  Mode,
  ControlAction,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ── Generic Fetch Wrapper ─────────────────────────────────

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new ApiError(
        response.status,
        errorBody || `HTTP ${response.status}: ${response.statusText}`
      );
    }

    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new ApiError(0, 'Network error — backend unreachable');
    }
    throw new ApiError(500, `Request failed: ${(error as Error).message}`);
  }
}

// ── Status & Health ───────────────────────────────────────

export async function getStatus(): Promise<SystemStatus> {
  return fetchAPI<SystemStatus>('/api/status');
}

export async function getHealth(): Promise<{
  status: string;
  timestamp: string;
  broker: { status: string; latency_ms: number | null };
  database: { status: string; latency_ms: number | null };
}> {
  return fetchAPI('/api/health');
}

// ── Positions ─────────────────────────────────────────────

export async function getPositions(): Promise<Position[]> {
  return fetchAPI<Position[]>('/api/positions');
}

export async function getPositionCount(): Promise<{ count: number }> {
  return fetchAPI<{ count: number }>('/api/positions/count');
}

// ── Trades ────────────────────────────────────────────────

export async function getTrades(params?: {
  limit?: number;
  symbol?: string;
  strategy?: string;
  result?: string;
}): Promise<Trade[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.symbol) searchParams.set('symbol', params.symbol);
  if (params?.strategy) searchParams.set('strategy', params.strategy);
  if (params?.result) searchParams.set('result', params.result);

  const query = searchParams.toString();
  return fetchAPI<Trade[]>(`/api/trades${query ? `?${query}` : ''}`);
}

export async function getTradeStats(days: number = 30): Promise<{
  period_days: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
  profit_factor: number;
}> {
  return fetchAPI(`/api/trades/stats?days=${days}`);
}

// ── Signals ───────────────────────────────────────────────

export async function getSignals(params?: {
  limit?: number;
  symbol?: string;
}): Promise<Signal[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.symbol) searchParams.set('symbol', params.symbol);

  const query = searchParams.toString();
  return fetchAPI<Signal[]>(`/api/signals${query ? `?${query}` : ''}`);
}

// ── Strategies ────────────────────────────────────────────

export async function getStrategies(params?: {
  status?: string;
  min_trades?: number;
}): Promise<Strategy[]> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.min_trades) searchParams.set('min_trades', params.min_trades.toString());

  const query = searchParams.toString();
  return fetchAPI<Strategy[]>(`/api/strategies${query ? `?${query}` : ''}`);
}

// ── Performance ───────────────────────────────────────────

export async function getPerformance(): Promise<PerformanceSummary> {
  return fetchAPI<PerformanceSummary>('/api/performance');
}

// ── Evolution ─────────────────────────────────────────────

export async function getEvolution(limit: number = 20): Promise<EvolutionEvent[]> {
  return fetchAPI<EvolutionEvent[]>(`/api/evolution?limit=${limit}`);
}

// ── Audit ─────────────────────────────────────────────────

export async function getAudit(params?: {
  limit?: number;
  event_type?: string;
}): Promise<AuditEntry[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.event_type) searchParams.set('event_type', params.event_type);

  const query = searchParams.toString();
  return fetchAPI<AuditEntry[]>(`/api/audit${query ? `?${query}` : ''}`);
}

export async function verifyAudit(): Promise<AuditVerification> {
  return fetchAPI<AuditVerification>('/api/audit/verify');
}

// ── Regime ────────────────────────────────────────────────

export async function getRegime(pair: string = 'EURUSD'): Promise<RegimeClassification> {
  return fetchAPI<RegimeClassification>(`/api/regime?pair=${pair}`);
}

// ── Snapshots ─────────────────────────────────────────────

export async function getSnapshots(limit: number = 30): Promise<EquityPoint[]> {
  return fetchAPI<EquityPoint[]>(`/api/snapshots?limit=${limit}`);
}

// ── Events ────────────────────────────────────────────────

export async function getEvents(params?: {
  limit?: number;
  event_type?: string;
}): Promise<{ id: number; event_type: string; message: string; data: Record<string, unknown>; created_at: string }[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.event_type) searchParams.set('event_type', params.event_type);

  const query = searchParams.toString();
  return fetchAPI(`/api/events${query ? `?${query}` : ''}`);
}

// ── Governance ────────────────────────────────────────────

export async function getLastGovernance(): Promise<GovernanceDecision> {
  return fetchAPI<GovernanceDecision>('/api/governance/last');
}

// ── Risk ──────────────────────────────────────────────────

export async function getRiskSummary(): Promise<RiskSummary> {
  return fetchAPI<RiskSummary>('/api/risk/summary');
}

// ── Chat ──────────────────────────────────────────────────

export async function sendChatMessage(message: string): Promise<{ response: string }> {
  return fetchAPI<{ response: string }>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

// ── Control ───────────────────────────────────────────────

export async function sendControl(
  action: ControlAction,
  params?: Record<string, string>
): Promise<{ status: string; [key: string]: unknown }> {
  const searchParams = new URLSearchParams();
  searchParams.set('action', action);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      searchParams.set(key, value);
    });
  }

  return fetchAPI(`/api/control?${searchParams.toString()}`, {
    method: 'POST',
  });
}