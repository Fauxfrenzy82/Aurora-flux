'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { EquityChart } from '@/components/EquityChart';
import { PositionCard } from '@/components/PositionCard';
import { SignalFeed } from '@/components/SignalFeed';
import { StrategyTable } from '@/components/StrategyTable';
import { RiskGauges } from '@/components/RiskGauges';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn, formatCurrency, formatPercent, formatTimeAgo } from '@/lib/utils';
import { getTradeStats } from '@/lib/api';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  DollarSign,
  Clock,
  AlertCircle,
  RefreshCw,
  ChevronRight,
  Zap,
} from 'lucide-react';

export default function Dashboard() {
  const {
    equity,
    balance,
    dailyPnL,
    dailyPnLPct,
    positions,
    recentTrades,
    performance,
    regime,
    regimeConfidence,
    session,
    scalpModeActive,
    halted,
    lastUpdate,
    isRefreshing,
    setRefreshing,
    updateFromStatus,
  } = useSystemStore();

  const [tradeStats, setTradeStats] = React.useState<{
    win_rate: number;
    profit_factor: number;
    net_pnl: number;
    total_trades: number;
  } | null>(null);

  React.useEffect(() => {
    const fetchStats = async () => {
      const stats = await getTradeStats(30);
      setTradeStats(stats);
    };
    fetchStats();
  }, [recentTrades]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const { getStatus } = await import('@/lib/api');
      const status = await getStatus();
      updateFromStatus(status);
    } catch (error) {
      console.error('Refresh error:', error);
    } finally {
      setRefreshing(false);
    }
  };

  const recentWins = recentTrades.filter(t => t.result === 'WIN').length;
  const recentLosses = recentTrades.filter(t => t.result === 'LOSS').length;
  const recentWinRate = recentTrades.length > 0 ? recentWins / recentTrades.length : 0;

  // Top performers
  const topStrategies = (performance?.total_trades || 0) > 0
    ? [
        { name: 'Win Rate', value: formatPercent(performance?.win_rate || 0) },
        { name: 'Profit Factor', value: (performance?.profit_factor || 0).toFixed(2) },
        { name: 'Net P&L', value: formatCurrency(performance?.net_pnl || 0) },
      ]
    : [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-400">
            Last updated: {lastUpdate ? formatTimeAgo(lastUpdate) : 'Never'}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRefresh}
          loading={isRefreshing}
          icon={<RefreshCw className="h-4 w-4" />}
        >
          Refresh
        </Button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Equity"
          value={formatCurrency(equity)}
          subtitle={`Balance: ${formatCurrency(balance)}`}
          icon={<DollarSign className="h-5 w-5" />}
          trend={dailyPnL}
          trendLabel="Today"
          color="aurora"
        />
        <StatCard
          title="Drawdown"
          value={formatPercent(useSystemStore.getState().drawdownPct)}
          subtitle={`Max: ${formatPercent(0.06)}`}
          icon={<AlertCircle className="h-5 w-5" />}
          color={useSystemStore.getState().drawdownPct > 0.05 ? 'red' : 'yellow'}
        />
        <StatCard
          title="Win Rate (30d)"
          value={formatPercent(tradeStats?.win_rate || 0)}
          subtitle={`${tradeStats?.total_trades || 0} trades`}
          icon={<Activity className="h-5 w-5" />}
          color="aurora"
        />
        <StatCard
          title="Profit Factor"
          value={(tradeStats?.profit_factor || 0).toFixed(2)}
          subtitle={`Net: ${formatCurrency(tradeStats?.net_pnl || 0)}`}
          icon={<TrendingUp className="h-5 w-5" />}
          color="aurora"
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left Column */}
        <div className="lg:col-span-2 space-y-4">
          <EquityChart />

          {/* Recent Performance */}
          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-aurora-400" />
                  Recent Performance
                </span>
              </CardTitle>
              <div className="flex items-center gap-3 text-sm">
                <span className="text-green-400">
                  ▲ {recentWins}W
                </span>
                <span className="text-red-400">
                  ▼ {recentLosses}L
                </span>
                <Badge
                  variant={recentWinRate >= 0.5 ? 'success' : 'danger'}
                  size="sm"
                >
                  {formatPercent(recentWinRate)} WR
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {recentTrades.slice(0, 10).map((trade) => (
                  <RecentTradeItem key={trade.id} trade={trade} />
                ))}
                {recentTrades.length === 0 && (
                  <p className="text-center text-gray-500 py-4">No recent trades</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Top Strategies */}
          {topStrategies.length > 0 && (
            <Card variant="bordered" padding="md">
              <CardHeader>
                <CardTitle>Performance Snapshot</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-3">
                  {topStrategies.map((stat, i) => (
                    <div key={i} className="text-center p-2 bg-surface-700/50 rounded-lg">
                      <p className="text-xs text-gray-500">{stat.name}</p>
                      <p className="text-lg font-mono font-bold text-white">{stat.value}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column */}
        <div className="space-y-4">
          <RiskGauges />

          {/* Regime Card */}
          <Card variant="bordered" padding="md">
            <CardHeader>
              <CardTitle>Market State</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Regime</span>
                <Badge
                  variant={
                    regime.includes('TRENDING_UP') ? 'success' :
                    regime.includes('TRENDING_DOWN') ? 'danger' :
                    regime.includes('RANGE') ? 'warning' : 'neutral'
                  }
                  size="md"
                  dot
                >
                  {regime.replace(/_/g, ' ')}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Confidence</span>
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-aurora-500 rounded-full"
                      style={{ width: `${(regimeConfidence || 0) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono">{((regimeConfidence || 0) * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Session</span>
                <span className={`text-sm font-medium ${
                  session === 'LONDON' ? 'text-blue-400' :
                  session === 'NEW_YORK' ? 'text-orange-400' :
                  session === 'OVERLAP' ? 'text-purple-400' :
                  'text-yellow-400'
                }`}>
                  {session}
                </span>
              </div>
              {scalpModeActive && (
                <div className="mt-2 p-2 bg-yellow-500/10 rounded-lg border border-yellow-500/30 flex items-center gap-2">
                  <Zap className="h-4 w-4 text-yellow-400" />
                  <span className="text-xs text-yellow-400">Scalp Mode Active</span>
                </div>
              )}
              {halted && (
                <div className="mt-2 p-2 bg-red-500/10 rounded-lg border border-red-500/30 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-400" />
                  <span className="text-xs text-red-400">System Halted</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Open Positions Preview */}
          <Card variant="bordered" padding="md">
            <CardHeader>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-aurora-400" />
                  Open Positions
                </span>
              </CardTitle>
              <Badge variant="neutral" size="sm">
                {positions.length}
              </Badge>
            </CardHeader>
            <CardContent>
              {positions.length === 0 ? (
                <p className="text-center text-gray-500 py-4">No open positions</p>
              ) : (
                <div className="space-y-2">
                  {positions.slice(0, 3).map((pos) => (
                    <PositionCard key={pos.position_id} position={pos} />
                  ))}
                  {positions.length > 3 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      fullWidth
                      icon={<ChevronRight className="h-3 w-3" />}
                    >
                      View all {positions.length} positions
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendLabel,
  color = 'aurora',
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
  trend?: number;
  trendLabel?: string;
  color?: 'aurora' | 'green' | 'red' | 'yellow';
}) {
  const colorClasses = {
    aurora: 'text-aurora-400',
    green: 'text-green-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
  };

  return (
    <Card variant="elevated" padding="md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-mono font-bold text-white mt-1">{value}</p>
          <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
        </div>
        <div className={cn('p-2 rounded-lg bg-surface-700', colorClasses[color])}>
          {icon}
        </div>
      </div>
      {trend !== undefined && (
        <div className="flex items-center gap-1 mt-2">
          <span className={cn('text-xs font-medium', trend >= 0 ? 'text-green-400' : 'text-red-400')}>
            {trend >= 0 ? '+' : ''}{formatCurrency(trend)}
          </span>
          <span className="text-xs text-gray-500">{trendLabel}</span>
        </div>
      )}
    </Card>
  );
}

function RecentTradeItem({ trade }: { trade: any }) {
  const isWin = trade.result === 'WIN';

  return (
    <div className="flex items-center justify-between p-2 rounded-lg bg-surface-700/30 hover:bg-surface-700 transition-colors">
      <div className="flex items-center gap-3">
        <div className={cn(
          'h-8 w-8 rounded-full flex items-center justify-center',
          isWin ? 'bg-green-500/20' : 'bg-red-500/20'
        )}>
          {isWin ? (
            <TrendingUp className="h-4 w-4 text-green-400" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-400" />
          )}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white font-mono">{trade.symbol}</span>
            <Badge variant={isWin ? 'success' : 'danger'} size="sm">
              {trade.result}
            </Badge>
          </div>
          <p className="text-xs text-gray-500">{trade.strategy_name}</p>
        </div>
      </div>
      <div className="text-right">
        <p className={cn('text-sm font-mono font-bold', isWin ? 'text-green-400' : 'text-red-400')}>
          {isWin ? '+' : ''}{formatCurrency(trade.profit_currency)}
        </p>
        <p className="text-xs text-gray-500">{formatTimeAgo(trade.created_at)}</p>
      </div>
    </div>
  );
}