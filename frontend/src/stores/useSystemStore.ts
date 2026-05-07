/**
 * Zustand store — centralized state management for Aurora Flux frontend.
 * Updated via REST API polling and real-time WebSocket events.
 */

import { create } from 'zustand';
import type {
  SystemStatus,
  Position,
  Trade,
  Signal,
  Strategy,
  GovernanceDecision,
  RegimeType,
  Mode,
  ChatMessage,
  EquityPoint,
  PerformanceSummary,
  AccountInfo,
  WSMessage,
} from '@/types';
import { getWebSocket } from '@/lib/websocket';

interface SystemState {
  isConnected: boolean;
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'reconnecting';
  lastUpdate: string | null;
  error: string | null;
  equity: number;
  balance: number;
  dailyPnL: number;
  dailyPnLPct: number;
  equityHistory: EquityPoint[];
  accountInfo: AccountInfo | null;
  mode: Mode;
  phaseDay: number;
  phaseNumber: number;
  regime: RegimeType | string;
  regimeConfidence: number;
  session: string;
  scalpModeActive: boolean;
  marketOpen: boolean;
  halted: boolean;
  drawdownPct: number;
  maxDrawdownPct: number;
  riskOfRuin: number;
  totalExposurePct: number;
  dailyCapRemaining: number;
  positions: Position[];
  strategies: Strategy[];
  signals: Signal[];
  recentTrades: Trade[];
  lastGovernance: GovernanceDecision | null;
  performance: PerformanceSummary | null;
  chatMessages: ChatMessage[];
  isLoading: boolean;
  isRefreshing: boolean;
  selectedStrategy: Strategy | null;
  activeRoute: string;
  uptimeSeconds: number;

  setConnected: (connected: boolean) => void;
  setError: (error: string | null) => void;
  updateFromStatus: (status: SystemStatus) => void;
  updateEquity: (equity: number, balance: number, dailyPnL: number) => void;
  addPosition: (position: Position) => void;
  removePosition: (positionId: string) => void;
  updatePosition: (position: Position) => void;
  addSignal: (signal: Signal) => void;
  setStrategies: (strategies: Strategy[]) => void;
  setRecentTrades: (trades: Trade[]) => void;
  setEquityHistory: (history: EquityPoint[]) => void;
  setPerformance: (performance: PerformanceSummary) => void;
  addChatMessage: (message: ChatMessage) => void;
  setGovernance: (decision: GovernanceDecision) => void;
  setRegime: (regime: string, confidence: number) => void;
  setSession: (session: string) => void;
  toggleScalpMode: (active: boolean) => void;
  setMode: (mode: Mode) => void;
  setHalted: (halted: boolean) => void;
  setSelectedStrategy: (strategy: Strategy | null) => void;
  setActiveRoute: (route: string) => void;
  setRefreshing: (refreshing: boolean) => void;
  reset: () => void;
}

const initialState = {
  isConnected: false,
  connectionState: 'disconnected' as const,
  lastUpdate: null,
  error: null,
  equity: 10.0,
  balance: 10.0,
  dailyPnL: 0,
  dailyPnLPct: 0,
  equityHistory: [],
  accountInfo: null,
  mode: 'PHASE' as Mode,
  phaseDay: 1,
  phaseNumber: 1,
  regime: 'UNKNOWN',
  regimeConfidence: 0,
  session: 'UNKNOWN',
  scalpModeActive: false,
  marketOpen: true,
  halted: false,
  drawdownPct: 0,
  maxDrawdownPct: 0.06,
  riskOfRuin: 0,
  totalExposurePct: 0,
  dailyCapRemaining: 20,
  positions: [],
  strategies: [],
  signals: [],
  recentTrades: [],
  lastGovernance: null,
  performance: null,
  chatMessages: [],
  isLoading: true,
  isRefreshing: false,
  selectedStrategy: null,
  activeRoute: '/',
  uptimeSeconds: 0,
};

export const useSystemStore = create<SystemState>((set, get) => ({
  ...initialState,

  setConnected: (connected: boolean) =>
    set({ isConnected: connected, connectionState: connected ? 'connected' : 'disconnected' }),

  setError: (error: string | null) => set({ error }),

  updateFromStatus: (status: SystemStatus) =>
    set({
      equity: status?.equity ?? 10.0,
      balance: status?.balance ?? 10.0,
      mode: status?.mode ?? 'PHASE',
      phaseDay: status?.phase_day ?? 1,
      regime: status?.regime ?? 'UNKNOWN',
      regimeConfidence: status?.regime_confidence ?? 0,
      drawdownPct: status?.drawdown ?? 0,
      positions: Array.isArray(status?.positions) ? status.positions : [],
      dailyPnL: status?.daily_pnl ?? 0,
      dailyPnLPct: (status?.balance > 0) ? ((status?.daily_pnl ?? 0) / status.balance) * 100 : 0,
      session: status?.session ?? 'UNKNOWN',
      halted: status?.halted ?? false,
      scalpModeActive: status?.scalp_active ?? false,
      isConnected: status?.connected ?? false,
      lastUpdate: status?.last_update ?? new Date().toISOString(),
      uptimeSeconds: status?.uptime_seconds ?? 0,
      isLoading: false,
    }),

  updateEquity: (equity: number, balance: number, dailyPnL: number) =>
    set((state) => ({
      equity, balance, dailyPnL,
      dailyPnLPct: balance > 0 ? (dailyPnL / balance) * 100 : 0,
      equityHistory: [...state.equityHistory, { timestamp: new Date().toISOString(), equity }].slice(-200),
      lastUpdate: new Date().toISOString(),
    })),

  addPosition: (position: Position) =>
    set((state) => ({ positions: [position, ...state.positions] })),

  removePosition: (positionId: string) =>
    set((state) => ({ positions: state.positions.filter((p) => p.position_id !== positionId) })),

  updatePosition: (position: Position) =>
    set((state) => ({
      positions: state.positions.map((p) => (p.position_id === position.position_id ? position : p)),
    })),

  addSignal: (signal: Signal) =>
    set((state) => ({ signals: [signal, ...state.signals].slice(0, 100) })),

  setStrategies: (strategies: Strategy[]) => set({ strategies }),

  setRecentTrades: (trades: Trade[]) => set({ recentTrades: trades.slice(0, 50) }),

  setEquityHistory: (history: EquityPoint[]) => set({ equityHistory: history }),

  setPerformance: (performance: PerformanceSummary) => set({ performance }),

  addChatMessage: (message: ChatMessage) =>
    set((state) => ({ chatMessages: [...state.chatMessages, message].slice(-200) })),

  setGovernance: (decision: GovernanceDecision) => set({ lastGovernance: decision }),

  setRegime: (regime: string, confidence: number) => set({ regime, regimeConfidence: confidence }),

  setSession: (session: string) => set({ session }),

  toggleScalpMode: (active: boolean) => set({ scalpModeActive: active }),

  setMode: (mode: Mode) => set({ mode }),

  setHalted: (halted: boolean) => set({ halted }),

  setSelectedStrategy: (strategy: Strategy | null) => set({ selectedStrategy: strategy }),

  setActiveRoute: (route: string) => set({ activeRoute: route }),

  setRefreshing: (refreshing: boolean) => set({ isRefreshing: refreshing }),

  reset: () => set(initialState),
}));

let wsUnsubscribers: (() => void)[] = [];

export function initWebSocketStore(): void {
  wsUnsubscribers.forEach((unsub) => unsub());
  wsUnsubscribers = [];

  const ws = getWebSocket();
  const store = useSystemStore.getState;
  const setState = useSystemStore.setState;

  wsUnsubscribers.push(
    ws.on('equity_update', (data) => {
      setState({ equity: data.equity as number, balance: data.balance as number, dailyPnL: (data.daily_pnl as number) || 0, lastUpdate: new Date().toISOString() });
    }),
    ws.on('position_opened', (data) => {
      setState((state) => ({ positions: [data as unknown as Position, ...state.positions] }));
    }),
    ws.on('position_closed', (data) => {
      const positionId = data.position_id as string;
      setState((state) => ({ positions: state.positions.filter((p) => p.position_id !== positionId) }));
    }),
    ws.on('position_updated', (data) => {
      const position = data as unknown as Position;
      setState((state) => ({ positions: state.positions.map((p) => (p.position_id === position.position_id ? position : p)) }));
    }),
    ws.on('signal_generated', (data) => {
      setState((state) => ({ signals: [data as unknown as Signal, ...state.signals].slice(0, 100) }));
    }),
    ws.on('governance_decision', (data) => {
      setState({ lastGovernance: data as unknown as GovernanceDecision });
    }),
    ws.on('regime_changed', (data) => {
      setState({ regime: (data.regime as string) || 'UNKNOWN', regimeConfidence: (data.confidence as number) || 0 });
    }),
    ws.on('session_changed', (data) => {
      setState({ session: (data.session as string) || 'UNKNOWN' });
    }),
    ws.on('scalp_mode_toggled', (data) => {
      setState({ scalpModeActive: (data.active as boolean) || false });
    }),
    ws.on('error_alert', (data) => {
      setState({ error: (data.message as string) || 'Unknown error' });
      setTimeout(() => setState({ error: null }), 10000);
    }),
    ws.on('state_update', (data) => {
      const status = data as unknown as SystemStatus;
      store().updateFromStatus(status);
    })
  );

  ws.connect();
}