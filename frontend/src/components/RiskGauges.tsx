'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { cn, formatPercent, formatCurrency } from '@/lib/utils';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Target,
  AlertTriangle,
  TrendingDown,
  DollarSign,
} from 'lucide-react';

type SeverityLevel = 'safe' | 'warning' | 'danger' | 'critical';

export function RiskGauges() {
  const {
    drawdownPct,
    maxDrawdownPct,
    totalExposurePct,
    riskOfRuin,
    dailyPnL,
    balance,
    equity,
    halted,
  } = useSystemStore();

  const drawdownSeverity: SeverityLevel =
    maxDrawdownPct > 0
      ? drawdownPct / maxDrawdownPct > 0.9
        ? 'critical'
        : drawdownPct / maxDrawdownPct > 0.6
          ? 'danger'
          : drawdownPct / maxDrawdownPct > 0.3
            ? 'warning'
            : 'safe'
      : 'safe';

  const exposureSeverity: SeverityLevel =
    totalExposurePct > 45
      ? 'critical'
      : totalExposurePct > 35
        ? 'danger'
        : totalExposurePct > 20
          ? 'warning'
          : 'safe';

  const drawdownVariant: 'success' | 'warning' | 'danger' =
    drawdownSeverity === 'safe'
      ? 'success'
      : drawdownSeverity === 'warning'
        ? 'warning'
        : 'danger';

  const exposureVariant: 'success' | 'warning' | 'danger' =
    exposureSeverity === 'safe'
      ? 'success'
      : exposureSeverity === 'warning'
        ? 'warning'
        : 'danger';

  return (
    <Card variant={halted ? 'glow' : 'elevated'} padding="md">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            {halted ? (
              <ShieldAlert className="h-4 w-4 text-red-400 animate-pulse" />
            ) : (
              <Shield className="h-4 w-4 text-aurora-400" />
            )}
            Risk Overview
          </span>
        </CardTitle>
        {halted && (
          <Badge variant="danger" size="sm" dot pulse>
            HALTED
          </Badge>
        )}
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <GaugeCard
            icon={<TrendingDown className="h-5 w-5" />}
            label="Drawdown"
            value={formatPercent(drawdownPct)}
            subValue={`Max: ${formatPercent(maxDrawdownPct)}`}
            progress={drawdownPct / Math.max(maxDrawdownPct, 0.01) * 100}
            variant={drawdownVariant}
            severity={drawdownSeverity}
            warning={drawdownSeverity === 'critical' ? 'Approaching max drawdown' : undefined}
          />

          <GaugeCard
            icon={<Target className="h-5 w-5" />}
            label="Exposure"
            value={formatPercent(totalExposurePct / 100)}
            subValue="Max: 50%"
            progress={(totalExposurePct / 50) * 100}
            variant={exposureVariant}
            severity={exposureSeverity}
          />

          <GaugeCard
            icon={<AlertTriangle className="h-5 w-5" />}
            label="Risk of Ruin"
            value={riskOfRuin < 0.0001 ? '< 0.01%' : formatPercent(riskOfRuin)}
            subValue={riskOfRuin < 0.001 ? 'Safe' : 'Elevated'}
            progress={Math.min(100, riskOfRuin * 1000)}
            variant={riskOfRuin < 0.001 ? 'success' : 'warning'}
            severity={riskOfRuin < 0.001 ? 'safe' : 'warning'}
          />

          <GaugeCard
            icon={<DollarSign className="h-5 w-5" />}
            label="Daily P&L"
            value={formatCurrency(dailyPnL)}
            subValue={balance > 0 ? `${(dailyPnL / balance * 100).toFixed(2)}% of balance` : 'N/A'}
            progress={Math.min(100, Math.abs(dailyPnL) / Math.max(balance, 0.01) * 500)}
            variant={dailyPnL >= 0 ? 'success' : 'danger'}
            severity={dailyPnL >= 0 ? 'safe' : 'warning'}
          />
        </div>

        <div className="mt-4 p-3 bg-surface-700/50 rounded-lg">
          <h4 className="text-xs font-semibold text-gray-400 uppercase mb-2">Active Constraints</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <ConstraintBadge label="Max Risk" active={true} />
            <ConstraintBadge label="Daily Cap" active={true} />
            <ConstraintBadge label="Drawdown" active={drawdownSeverity !== 'safe'} />
            <ConstraintBadge label="Exposure" active={exposureSeverity !== 'safe'} />
            <ConstraintBadge label="Volatility" active={false} />
            <ConstraintBadge label="Regime" active={false} />
            <ConstraintBadge label="Correlation" active={false} />
            <ConstraintBadge label="Balance" active={false} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function GaugeCard({
  icon,
  label,
  value,
  subValue,
  progress,
  variant,
  severity,
  warning,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subValue: string;
  progress: number;
  variant: 'success' | 'warning' | 'danger';
  severity: SeverityLevel;
  warning?: string;
}) {
  const severityColors: Record<SeverityLevel, string> = {
    safe: 'text-green-400',
    warning: 'text-yellow-400',
    danger: 'text-orange-400',
    critical: 'text-red-400',
  };

  return (
    <div className="p-3 bg-surface-700/50 rounded-lg">
      <div className="flex items-center gap-2 mb-2">
        <span className={cn(severityColors[severity])}>
          {icon}
        </span>
        <span className="text-xs text-gray-400 uppercase">{label}</span>
      </div>
      <p className="text-lg font-mono font-bold text-white mb-1">{value}</p>
      <Progress value={Math.min(100, progress)} variant={variant} size="sm" showLabel={false} />
      <p className="text-xs text-gray-500 mt-1">{subValue}</p>
      {warning && <p className="text-xs text-red-400 mt-1 font-medium">{warning}</p>}
    </div>
  );
}

function ConstraintBadge({ label, active }: { label: string; active: boolean }) {
  return (
    <span className={cn('px-2 py-1 rounded-md font-medium text-center', active ? 'bg-aurora-600/20 text-aurora-400 border border-aurora-600/30' : 'bg-surface-700 text-gray-500')}>
      {label}{active && ' ✓'}
    </span>
  );
}