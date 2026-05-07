'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { RiskGauges } from '@/components/RiskGauges';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn,formatCurrency, formatPercent } from '@/lib/utils';
import {
  Shield,
  Target,
  AlertTriangle,
  TrendingDown,
  DollarSign,
  Activity,
  Clock,
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
  } = useSystemStore();

  // Calculate additional metrics
  const marginUsed = positions.reduce(
    (sum, p) => sum + Math.abs(p.volume) * p.current_price * 0.02,
    0
  );
  const marginLevel = marginUsed > 0 ? (equity / marginUsed) * 100 : 0;
  const availableMargin = equity - marginUsed;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Risk Management</h1>
        <p className="text-sm text-gray-400">Monitor position sizing, drawdown, and safety limits</p>
      </div>

      {/* Main Risk Gauges */}
      <RiskGauges />

      {/* Detailed Risk Metrics */}
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
            {/* Left Column */}
            <div className="space-y-4">
              <MetricRow
                label="Drawdown"
                value={formatPercent(drawdownPct)}
                max={formatPercent(maxDrawdownPct)}
                progress={(drawdownPct / maxDrawdownPct) * 100}
                variant={drawdownPct / maxDrawdownPct > 0.7 ? 'danger' : 'warning'}
              />
              <MetricRow
                label="Exposure"
                value={formatPercent(totalExposurePct / 100)}
                max="50% limit"
                progress={totalExposurePct / 50 * 100}
                variant={totalExposurePct / 50 > 0.7 ? 'danger' : 'warning'}
              />
              <MetricRow
                label="Risk of Ruin"
                value={riskOfRuin < 0.0001 ? '< 0.01%' : formatPercent(riskOfRuin)}
                max="2% limit"
                progress={Math.min(100, riskOfRuin * 1000)}
                variant={riskOfRuin > 0.01 ? 'danger' : 'success'}
              />
              <MetricRow
                label="Margin Level"
                value={`${marginLevel.toFixed(0)}%`}
                max="Below 100% = margin call"
                progress={Math.min(100, marginLevel)}
                variant={marginLevel < 150 ? 'danger' : marginLevel < 300 ? 'warning' : 'success'}
              />
            </div>

            {/* Right Column */}
            <div className="space-y-4">
              <MetricRow
                label="Daily P&L"
                value={formatCurrency(dailyPnL)}
                max={formatPercent(dailyPnLPct / 100)}
                progress={Math.min(100, Math.abs(dailyPnL) / Math.max(equity, 1) * 500)}
                variant={dailyPnLPct < -5 ? 'danger' : dailyPnLPct < -2 ? 'warning' : 'success'}
                isCurrency
                isProfit={dailyPnL >= 0}
              />
              <MetricRow
                label="Available Margin"
                value={formatCurrency(availableMargin)}
                max={`${formatPercent(availableMargin / Math.max(equity, 1))} of equity`}
                progress={Math.min(100, (availableMargin / Math.max(equity, 1)) * 100)}
                variant="success"
                isCurrency
              />
              <MetricRow
                label="Open Positions"
                value={positions.length.toString()}
                max="Max 5"
                progress={(positions.length / 5) * 100}
                variant={positions.length >= 5 ? 'danger' : positions.length >= 4 ? 'warning' : 'success'}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Active Safety Limits */}
      <Card variant="bordered" padding="md">
        <CardHeader>
          <CardTitle>
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-yellow-400" />
              Active Safety Limits
            </span>
          </CardTitle>
          {halted && (
            <Badge variant="danger" size="sm" dot pulse>
              SYSTEM HALTED
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SafetyLimit
              label="Max Drawdown"
              value={formatPercent(maxDrawdownPct)}
              status={drawdownPct / maxDrawdownPct > 0.9 ? 'critical' : 'active'}
            />
            <SafetyLimit
              label="Daily Cap (Phase)"
              value="20%"
              status={Math.abs(dailyPnLPct) > 15 ? 'warning' : 'active'}
            />
            <SafetyLimit
              label="Max Exposure"
              value="50%"
              status={totalExposurePct > 45 ? 'critical' : totalExposurePct > 35 ? 'warning' : 'active'}
            />
            <SafetyLimit
              label="Max Positions"
              value="5"
              status={positions.length >= 5 ? 'critical' : positions.length >= 4 ? 'warning' : 'active'}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricRow({
  label,
  value,
  max,
  progress,
  variant,
  isCurrency = false,
  isProfit = true,
}: {
  label: string;
  value: string;
  max: string;
  progress: number;
  variant: 'success' | 'warning' | 'danger';
  isCurrency?: boolean;
  isProfit?: boolean;
}) {
  const variantColors = {
    success: 'text-green-400',
    warning: 'text-yellow-400',
    danger: 'text-red-400',
  };

  const progressVariant = variant === 'success' ? 'success' : variant === 'warning' ? 'warning' : 'danger';

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-gray-400">{label}</span>
        <span className={cn('text-sm font-mono font-bold', variantColors[variant])}>
          {value}
        </span>
      </div>
      <Progress
        value={Math.min(100, isFinite(progress) ? progress : 0)}
        variant={progressVariant}
        size="sm"
        showLabel={false}
      />
      <p className="text-xs text-gray-500 mt-1">Max: {max}</p>
    </div>
  );
}

function SafetyLimit({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: 'active' | 'warning' | 'critical';
}) {
  const statusColors = {
    active: 'border-green-500/30 bg-green-500/10 text-green-400',
    warning: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400',
    critical: 'border-red-500/30 bg-red-500/10 text-red-400 animate-pulse',
  };

  const statusIcons = {
    active: '✓',
    warning: '⚠',
    critical: '🚨',
  };

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