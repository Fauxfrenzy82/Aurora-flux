'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { RiskGauges } from '@/components/RiskGauges';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn, formatCurrency, formatPercent } from '@/lib/utils';
import { sendControl } from '@/lib/api';
import {
  Shield,
  Target,
  AlertTriangle,
  TrendingDown,
  DollarSign,
  Activity,
  Clock,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

export default function RiskPage() {
  const {
    equity,
    balance,
    drawdownPct,
    maxDrawdownPct,
    totalExposurePct,
    riskOfRuin,
    dailyPnL,
    dailyPnLPct,
    positions,
    halted,
    setHalted,
  } = useSystemStore();

  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

  const marginUsed = positions.reduce(
    (sum, p) => sum + Math.abs(p.volume) * p.current_price * 0.02,
    0
  );
  const marginLevel = marginUsed > 0 ? (equity / marginUsed) * 100 : 0;
  const availableMargin = equity - marginUsed;

  const handleHalt = async () => {
    setActionLoading('halt');
    try {
      await sendControl('halt', { reason: 'Manual halt from dashboard' });
      setHalted(true);
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  const handleResume = async () => {
    setActionLoading('resume');
    try {
      await sendControl('resume');
      setHalted(false);
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  const handleCloseAll = async () => {
    setActionLoading('close_all');
    try {
      await sendControl('close_all');
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  const handleEmergency = async () => {
    setActionLoading('emergency');
    try {
      await sendControl('emergency');
      setHalted(true);
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Risk Management</h1>
        <p className="text-sm text-gray-400">Monitor position sizing, drawdown, and safety limits</p>
      </div>

      <RiskGauges />

      {/* Emergency Controls */}
      <Card variant="bordered" padding="md" className="border-red-500/30">
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="h-5 w-5" />
              Emergency Controls
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-gray-400 mb-4">
            These actions take immediate effect. Use with caution.
            Hold buttons for 3 seconds to confirm.
          </p>
          <div className="flex flex-wrap gap-3">
            {halted ? (
              <Button
                variant="primary"
                size="md"
                onClick={handleResume}
                loading={actionLoading === 'resume'}
                icon={<ShieldCheck className="h-4 w-4" />}
              >
                Resume Trading
              </Button>
            ) : (
              <Button
                variant="danger"
                size="md"
                holdDuration={3000}
                onClick={handleHalt}
                disabled={actionLoading !== null}
                icon={<ShieldAlert className="h-4 w-4" />}
              >
                Hold to Halt All Trading
              </Button>
            )}
            <Button
              variant="danger"
              size="md"
              holdDuration={3000}
              onClick={handleCloseAll}
              disabled={actionLoading !== null}
              icon={<TrendingDown className="h-4 w-4" />}
            >
              Hold to Close All Positions
            </Button>
            <Button
              variant="danger"
              size="md"
              holdDuration={3000}
              onClick={handleEmergency}
              disabled={actionLoading !== null}
              icon={<AlertTriangle className="h-4 w-4" />}
            >
              Hold for Emergency Shutdown
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card variant="elevated" padding="md">
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-aurora-400" />
              Detailed Metrics
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <MetricRow label="Drawdown" value={formatPercent(drawdownPct)} max={formatPercent(maxDrawdownPct)} progress={(drawdownPct / maxDrawdownPct) * 100} variant={drawdownPct / maxDrawdownPct > 0.7 ? 'danger' : 'warning'} />
              <MetricRow label="Exposure" value={formatPercent(totalExposurePct / 100)} max="50% limit" progress={totalExposurePct / 50 * 100} variant={totalExposurePct / 50 > 0.7 ? 'danger' : 'warning'} />
              <MetricRow label="Risk of Ruin" value={riskOfRuin < 0.0001 ? '< 0.01%' : formatPercent(riskOfRuin)} max="2% limit" progress={Math.min(100, riskOfRuin * 1000)} variant={riskOfRuin > 0.01 ? 'danger' : 'success'} />
              <MetricRow label="Margin Level" value={`${marginLevel.toFixed(0)}%`} max="Below 100% = margin call" progress={Math.min(100, marginLevel)} variant={marginLevel < 150 ? 'danger' : marginLevel < 300 ? 'warning' : 'success'} />
            </div>
            <div className="space-y-4">
              <MetricRow label="Daily P&L" value={formatCurrency(dailyPnL)} max={formatPercent(dailyPnLPct / 100)} progress={Math.min(100, Math.abs(dailyPnL) / Math.max(equity, 1) * 500)} variant={dailyPnLPct < -5 ? 'danger' : dailyPnLPct < -2 ? 'warning' : 'success'} />
              <MetricRow label="Available Margin" value={formatCurrency(availableMargin)} max={`${formatPercent(availableMargin / Math.max(equity, 1))} of equity`} progress={Math.min(100, (availableMargin / Math.max(equity, 1)) * 100)} variant="success" />
              <MetricRow label="Open Positions" value={positions.length.toString()} max="Max 5" progress={(positions.length / 5) * 100} variant={positions.length >= 5 ? 'danger' : positions.length >= 4 ? 'warning' : 'success'} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card variant="bordered" padding="md">
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-400" />
              Active Safety Limits
            </span>
          </CardTitle>
          {halted && <Badge variant="danger" size="sm" dot pulse>SYSTEM HALTED</Badge>}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SafetyLimit label="Max Drawdown" value={formatPercent(maxDrawdownPct)} status={drawdownPct / maxDrawdownPct > 0.9 ? 'critical' : 'active'} />
            <SafetyLimit label="Daily Cap (Phase)" value="20%" status={Math.abs(dailyPnLPct) > 15 ? 'warning' : 'active'} />
            <SafetyLimit label="Max Exposure" value="50%" status={totalExposurePct > 45 ? 'critical' : totalExposurePct > 35 ? 'warning' : 'active'} />
            <SafetyLimit label="Max Positions" value="5" status={positions.length >= 5 ? 'critical' : positions.length >= 4 ? 'warning' : 'active'} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricRow({ label, value, max, progress, variant }: {
  label: string; value: string; max: string; progress: number; variant: 'success' | 'warning' | 'danger';
}) {
  const variantColors = { success: 'text-green-400', warning: 'text-yellow-400', danger: 'text-red-400' };
  const progressVariant = variant === 'success' ? 'success' : variant === 'warning' ? 'warning' : 'danger';
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-gray-400">{label}</span>
        <span className={cn('text-sm font-mono font-bold', variantColors[variant])}>{value}</span>
      </div>
      <Progress value={Math.min(100, isFinite(progress) ? progress : 0)} variant={progressVariant} size="sm" showLabel={false} />
      <p className="text-xs text-gray-500 mt-1">Max: {max}</p>
    </div>
  );
}

function SafetyLimit({ label, value, status }: {
  label: string; value: string; status: 'active' | 'warning' | 'critical';
}) {
  const statusColors = {
    active: 'border-green-500/30 bg-green-500/10 text-green-400',
    warning: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400',
    critical: 'border-red-500/30 bg-red-500/10 text-red-400 animate-pulse',
  };
  const statusIcons = { active: '✓', warning: '⚠', critical: '🚨' };
  return (
    <div className={cn('p-3 rounded-lg border', statusColors[status])}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs uppercase tracking-wider">{label}</span>
        <span className="text-xs font-mono">{statusIcons[status]}</span>
      </div>
      <p className="text-lg font-mono font-bold">{value}</p>
    </div>
  );
}