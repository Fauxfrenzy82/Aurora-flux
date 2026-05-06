-- ============================================================
-- Aurora Flux — Complete Database Schema
-- Run in Supabase SQL Editor
-- ============================================================

-- Enable extensions
create extension if not exists "uuid-ossp";

-- ============================================================
-- TRADES — Completed trade records
-- ============================================================
create table if not exists trades (
  id bigserial primary key,
  trade_id text unique not null,
  symbol text not null,
  strategy_name text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  regime text,
  session text,
  entry_price numeric(12,6),
  exit_price numeric(12,6),
  stop_loss numeric(12,6),
  take_profit numeric(12,6),
  profit_pips numeric(10,2),
  profit_currency numeric(12,2),
  result text check (result in ('WIN', 'LOSS', 'BREAKEVEN', null)),
  confidence numeric(4,3),
  expected_value numeric(10,4),
  risk_amount numeric(10,2),
  risk_pct numeric(6,4),
  spread_at_entry numeric(8,4),
  volatility_at_entry numeric(8,4),
  reasoning text,
  attribution jsonb default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_trades_symbol on trades(symbol);
create index if not exists idx_trades_strategy on trades(strategy_name);
create index if not exists idx_trades_result on trades(result) where result is not null;
create index if not exists idx_trades_created on trades(created_at desc);
create index if not exists idx_trades_regime on trades(regime);
create index if not exists idx_trades_session on trades(session);

-- ============================================================
-- SIGNALS — Generated trading signals with governance results
-- ============================================================
create table if not exists signals (
  id bigserial primary key,
  signal_id text unique not null,
  symbol text not null,
  strategy_name text not null,
  strategy_id text,
  direction text not null check (direction in ('LONG', 'SHORT')),
  entry_price numeric(12,6),
  stop_loss numeric(12,6),
  take_profit numeric(12,6),
  confidence numeric(4,3),
  expected_value numeric(10,4),
  governance_result text check (governance_result in ('APPROVED', 'REJECTED', 'PENDING')),
  rejection_reason text,
  regime text,
  session text,
  created_at timestamptz default now()
);

create index if not exists idx_signals_symbol on signals(symbol);
create index if not exists idx_signals_governance on signals(governance_result);
create index if not exists idx_signals_created on signals(created_at desc);
create index if not exists idx_signals_strategy on signals(strategy_id);

-- ============================================================
-- STRATEGIES — Evolvable trading strategies
-- ============================================================
create table if not exists strategies (
  strategy_id text primary key,
  strategy_name text not null,
  status text default 'TESTING' check (status in ('ACTIVE', 'TESTING', 'SUSPENDED', 'RETIRED')),
  generation int default 0,
  birth_type text check (birth_type in ('SEED', 'BRED', 'MUTATED', null)),
  win_rate numeric(5,4) default 0,
  profit_factor numeric(8,2) default 0,
  sharpe_ratio numeric(8,4) default 0,
  total_trades int default 0,
  expectancy numeric(10,4) default 0,
  current_weight numeric(6,4) default 0,
  dna jsonb default '{}',
  compatible_regimes jsonb default '[]',
  preferred_sessions jsonb default '[]',
  preferred_pairs jsonb default '[]',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_strategies_status on strategies(status);
create index if not exists idx_strategies_win_rate on strategies(win_rate desc);
create index if not exists idx_strategies_profit_factor on strategies(profit_factor desc);

-- ============================================================
-- STRATEGY WEIGHT CHANGES — Audit trail for weight adjustments
-- ============================================================
create table if not exists strategy_weights (
  id bigserial primary key,
  strategy_id text not null references strategies(strategy_id) on delete cascade,
  old_weight numeric(6,4),
  new_weight numeric(6,4),
  reason text,
  created_at timestamptz default now()
);

create index if not exists idx_strategy_weights_id on strategy_weights(strategy_id);
create index if not exists idx_strategy_weights_created on strategy_weights(created_at desc);

-- ============================================================
-- ACCOUNT SNAPSHOTS — Periodic account state recording
-- ============================================================
create table if not exists account_snapshots (
  id bigserial primary key,
  balance numeric(14,2),
  equity numeric(14,2),
  margin numeric(14,2),
  free_margin numeric(14,2),
  open_positions int,
  exposure_pct numeric(8,4),
  daily_pnl numeric(10,2),
  unrealized_pnl numeric(10,2),
  mode text,
  phase_day int,
  created_at timestamptz default now()
);

create index if not exists idx_snapshots_created on account_snapshots(created_at desc);

-- ============================================================
-- AUDIT LEDGER — Tamper-evident audit chain
-- ============================================================
create table if not exists audit_ledger (
  id bigserial primary key,
  event_type text not null,
  data jsonb default '{}',
  hash text not null,
  prev_hash text default '',
  created_at timestamptz default now()
);

create index if not exists idx_audit_type on audit_ledger(event_type);
create index if not exists idx_audit_created on audit_ledger(created_at desc);
create index if not exists idx_audit_hash on audit_ledger(hash);

-- ============================================================
-- SYSTEM EVENTS — Operational event log
-- ============================================================
create table if not exists system_events (
  id bigserial primary key,
  event_type text not null,
  message text,
  data jsonb default '{}',
  created_at timestamptz default now()
);

create index if not exists idx_events_type on system_events(event_type);
create index if not exists idx_events_created on system_events(created_at desc);

-- ============================================================
-- REGIME HISTORY — Market regime detection log
-- ============================================================
create table if not exists regime_history (
  id bigserial primary key,
  pair text not null,
  regime text not null,
  confidence numeric(4,3),
  metrics jsonb default '{}',
  created_at timestamptz default now()
);

create index if not exists idx_regime_pair on regime_history(pair);
create index if not exists idx_regime_created on regime_history(created_at desc);
create index if not exists idx_regime_type on regime_history(regime);

-- ============================================================
-- PATTERN LIBRARY — Discovered market patterns
-- ============================================================
create table if not exists pattern_library (
  signature text primary key,
  description text,
  occurrences int default 0,
  wins int default 0,
  losses int default 0,
  win_rate numeric(5,4) default 0,
  avg_win numeric(10,2) default 0,
  avg_loss numeric(10,2) default 0,
  profit_factor numeric(8,2) default 0,
  status text default 'ACTIVE' check (status in ('ACTIVE', 'DORMANT', 'RETIRED')),
  discovered_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_patterns_status on pattern_library(status);
create index if not exists idx_patterns_win_rate on pattern_library(win_rate desc);

-- ============================================================
-- EVOLUTION LOG — Strategy evolution cycle records
-- ============================================================
create table if not exists evolution_log (
  id bigserial primary key,
  event_type text not null,
  description text,
  parent_ids jsonb default '[]',
  child_id text,
  reason text,
  created_at timestamptz default now()
);

create index if not exists idx_evolution_created on evolution_log(created_at desc);
create index if not exists idx_evolution_type on evolution_log(event_type);

-- ============================================================
-- PRINCIPLES — Extracted trading principles
-- ============================================================
create table if not exists principles (
  id bigserial primary key,
  principle_text text not null,
  confidence numeric(4,3),
  evidence_count int default 0,
  applicable_pairs jsonb default '[]',
  applicable_regimes jsonb default '[]',
  status text default 'ACTIVE' check (status in ('ACTIVE', 'DORMANT')),
  created_at timestamptz default now()
);

create index if not exists idx_principles_status on principles(status);

-- ============================================================
-- COGNITIVE LOG — Advanced reasoning events
-- ============================================================
create table if not exists cognitive_log (
  id bigserial primary key,
  event_type text not null,
  description text,
  data jsonb default '{}',
  created_at timestamptz default now()
);

create index if not exists idx_cognitive_type on cognitive_log(event_type);
create index if not exists idx_cognitive_created on cognitive_log(created_at desc);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- Allow service role full access (default behavior)
-- Allow anon key read-only on public-facing tables
-- ============================================================
alter table trades enable row level security;
alter table signals enable row level security;
alter table strategies enable row level security;
alter table account_snapshots enable row level security;
alter table system_events enable row level security;
alter table regime_history enable row level security;
alter table pattern_library enable row level security;
alter table evolution_log enable row level security;
alter table principles enable row level security;

-- Public read policies for frontend access
create policy "Allow public read trades"
  on trades for select
  using (true);

create policy "Allow public read signals"
  on signals for select
  using (true);

create policy "Allow public read strategies"
  on strategies for select
  using (true);

create policy "Allow public read snapshots"
  on account_snapshots for select
  using (true);

create policy "Allow public read events"
  on system_events for select
  using (true);

create policy "Allow public read regime history"
  on regime_history for select
  using (true);

create policy "Allow public read patterns"
  on pattern_library for select
  using (true);

create policy "Allow public read evolution log"
  on evolution_log for select
  using (true);

create policy "Allow public read principles"
  on principles for select
  using (true);

-- ============================================================
-- USEFUL VIEWS
-- ============================================================

-- Strategy performance summary
create or replace view strategy_performance as
select
  strategy_id,
  strategy_name,
  status,
  generation,
  birth_type,
  win_rate,
  profit_factor,
  sharpe_ratio,
  total_trades,
  expectancy,
  current_weight,
  case
    when total_trades >= 20 and win_rate >= 0.55 and profit_factor >= 1.5 then 'PROMOTABLE'
    when total_trades >= 10 and win_rate < 0.35 then 'AT_RISK'
    when status = 'SUSPENDED' then 'SUSPENDED'
    else 'NEUTRAL'
  end as recommendation,
  updated_at
from strategies;

-- Daily P&L summary
create or replace view daily_summary as
select
  date(created_at) as trade_date,
  count(*) as total_trades,
  count(*) filter (where result = 'WIN') as wins,
  count(*) filter (where result = 'LOSS') as losses,
  count(*) filter (where result = 'BREAKEVEN') as breakeven,
  sum(profit_currency) as net_pnl,
  sum(profit_currency) filter (where result = 'WIN') as gross_profit,
  abs(sum(profit_currency) filter (where result = 'LOSS')) as gross_loss,
  case
    when abs(sum(profit_currency) filter (where result = 'LOSS')) > 0
    then sum(profit_currency) filter (where result = 'WIN') /
         abs(sum(profit_currency) filter (where result = 'LOSS'))
    else null
  end as profit_factor,
  round(
    (count(*) filter (where result = 'WIN')::numeric / nullif(count(*), 0)) * 100, 2
  ) as win_rate_pct
from trades
group by date(created_at)
order by trade_date desc;