// ── Core Types ────────────────────────────────────────────

export type Mode = 'PHASE' | 'FREEDOM';
export type Direction = 'LONG' | 'SHORT';
export type TradeResult = 'WIN' | 'LOSS' | 'BREAKEVEN';
export type StrategyStatus = 'ACTIVE' | 'TESTING' | 'SUSPENDED' | 'RETIRED';
export type GovernanceResult = 'APPROVED' | 'REJECTED' | 'PENDING';
export type BirthType = 'SEED' | 'BRED' | 'MUTATED';
export type ImpactLevel = 'HIGH' | 'MEDIUM' | 'LOW';
export type RegimeType =
  | 'TRENDING_UP'
  | 'TRENDING_DOWN'
  | 'STRONG_TREND_UP'
  | 'STRONG_TREND_DOWN'
  | 'RANGE_BOUND'
  | 'VOLATILITY_EXPANSION'
  | 'VOLATILITY_CONTRACTION'
  | 'TRANSITION'
  | 'RISK_OFF'
  | 'UNCERTAIN';

// ── Account ───────────────────────────────────────────────

export interface AccountInfo {
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  currency: string;
  leverage: number;
  margin_level: number;
}

// ── Position ──────────────────────────────────────────────

export interface Position {
  position_id: string;
  symbol: string;
  direction: Direction;
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  profit: number;
  swap: number;
  commission: number;
  unrealized_pips: number;
  comment: string;
  open_time: string;
}

// ── Trade ─────────────────────────────────────────────────

export interface Trade {
  id: number;
  trade_id: string;
  symbol: string;
  strategy_name: string;
  direction: Direction;
  regime: string | null;
  session: string | null;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  take_profit: number;
  profit_pips: number;
  profit_currency: number;
  result: TradeResult | null;
  confidence: number;
  risk_amount: number;
  risk_pct: number;
  created_at: string;
  updated_at: string;
}

// ── Signal ────────────────────────────────────────────────

export interface Signal {
  signal_id: string;
  symbol: string;
  strategy_name: string;
  strategy_id: string;
  direction: Direction;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  confidence: number;
  governance_result: GovernanceResult;
  rejection_reason: string | null;
  regime: string;
  session: string;
  created_at: string;
}

// ── Strategy ──────────────────────────────────────────────

export interface Strategy {
  strategy_id: string;
  strategy_name: string;
  status: StrategyStatus;
  generation: number;
  birth_type: BirthType | null;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  total_trades: number;
  expectancy: number;
  current_weight: number;
  dna: StrategyDNA;
  compatible_regimes: string[];
  preferred_sessions: string[];
  preferred_pairs: string[];
  created_at: string;
  updated_at: string;
}

export interface StrategyDNA {
  strategy_id: string;
  strategy_name: string;
  entry: EntryCondition[];
  exit: EntryCondition[];
  stop: RiskMethod;
  profit: RiskMethod;
  trailing: RiskMethod | null;
  tf: string;
  confirm_tf: string;
  session: string;
  regime: string;
  pairs: string[];
  holding_min: number;
  holding_min_min: number;
  aggression: number;
  pyramiding: boolean;
  max_layers: number;
  hedging: boolean;
  reverse_signals: boolean;
}

export interface EntryCondition {
  indicator: string;
  operator: string;
  value: number;
  timeframe: string;
}

export interface RiskMethod {
  method: string;
  value: number;
}

// ── Governance ────────────────────────────────────────────

export interface GovernanceDecision {
  approved: boolean;
  reason: string;
  checkpoints: CheckpointResult[];
}

export interface CheckpointResult {
  name: string;
  passed: boolean;
  detail: string;
}

// ── Risk ──────────────────────────────────────────────────

export interface RiskSummary {
  drawdown: number;
  max_drawdown: number;
  exposure: number;
  max_exposure: number;
  risk_of_ruin: number;
  kelly_fraction: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  binding_constraint: string | null;
}

// ── Evolution ─────────────────────────────────────────────

export interface EvolutionEvent {
  id: number;
  event_type: string;
  description: string;
  parent_ids: string[];
  child_id: string | null;
  reason: string;
  created_at: string;
}

// ── Regime ────────────────────────────────────────────────

export interface RegimeClassification {
  regime: RegimeType;
  confidence: number;
  timestamp: string;
  adx: number;
  ema_alignment: number;
  volatility_ratio: number;
  volume_ratio: number;
  is_transitioning: boolean;
  regime_duration_bars: number;
  tradeable: boolean;
}

// ── Audit ─────────────────────────────────────────────────

export interface AuditEntry {
  id: number;
  event_type: string;
  data: Record<string, unknown>;
  hash: string;
  prev_hash: string;
  created_at: string;
}

export interface AuditVerification {
  valid: boolean;
  entries: number;
  errors: AuditError[];
}

export interface AuditError {
  type: string;
  entry_id?: number;
  expected_hash?: string;
  actual_hash?: string;
  expected_prev?: string;
  actual_prev?: string;
  message?: string;
}

// ── System Status ─────────────────────────────────────────

export interface SystemStatus {
  equity: number;
  balance: number;
  mode: Mode;
  phase_day: number;
  regime: string;
  regime_confidence: number;
  drawdown: number;
  positions: Position[];
  daily_pnl: number;
  daily_trades: number;
  connected: boolean;
  session: string;
  halted: boolean;
  scalp_active: boolean;
  last_update: string;
  uptime_seconds: number;
  governance: GovernanceStats;
}

export interface GovernanceStats {
  halted: boolean;
  halt_reason: string;
  total_evaluated: number;
  approved: number;
  rejected: number;
  approval_rate: number;
}

// ── Chat ──────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: 'user' | 'system' | 'assistant';
  content: string;
  timestamp: string;
  category?: 'status' | 'trade' | 'strategy' | 'risk' | 'evolution' | 'market' | 'control';
}

// ── Performance ───────────────────────────────────────────

export interface PerformanceSummary {
  total_trades: number;
  total_wins: number;
  total_losses: number;
  win_rate: number;
  total_profit: number;
  total_loss: number;
  net_pnl: number;
  profit_factor: number;
  active_strategies: number;
  total_strategies: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

// ── WebSocket Events ──────────────────────────────────────

export type WSEventType =
  | 'state_update'
  | 'equity_update'
  | 'position_opened'
  | 'position_closed'
  | 'position_updated'
  | 'signal_generated'
  | 'governance_decision'
  | 'trade_executed'
  | 'trade_closed'
  | 'regime_changed'
  | 'session_changed'
  | 'scalp_mode_toggled'
  | 'evolution_event'
  | 'error_alert'
  | 'heartbeat';

export interface WSMessage {
  type: WSEventType;
  data: Record<string, unknown>;
  timestamp: string;
}

// ── Control Actions ───────────────────────────────────────

export type ControlAction =
  | 'halt'
  | 'resume'
  | 'close_all'
  | 'emergency'
  | 'switch_mode';

// ── Store ─────────────────────────────────────────────────

export {};

declare global {
  interface Window {
    __AURORA_FLUX__: {
      version: string;
      apiUrl: string;
      wsUrl: string;
    };
  }
}