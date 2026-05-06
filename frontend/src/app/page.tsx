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