'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { PositionCard } from '@/components/PositionCard';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatPercent } from '@/lib/utils';
import { Layers, TrendingUp, TrendingDown, DollarSign, AlertCircle } from 'lucide-react';

export default function PositionsPage() {
  const { positions, equity, balance } = useSystemStore();

  const totalExposure = positions.reduce(
    (sum, p) => sum + Math.abs(p.volume) * p.current_price,
    0
  );
  const totalUnrealizedPnL = positions.reduce((sum, p) => sum + p.profit, 0);
  const exposurePct = equity > 0 ? (totalExposure / equity) * 100 : 0;

  const groupedByDirection = {
    LONG: positions.filter((p) => p.direction === 'LONG'),
    SHORT: positions.filter((p) => p.direction === 'SHORT'),
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Positions</h1>
        <p className="text-sm text-gray-400">Monitor and manage open trades</p>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryStat
          title="Total Positions"
          value={positions.length}
          icon={<Layers className="h-5 w-5" />}
          color="aurora"
        />
        <SummaryStat
          title="Total Exposure"
          value={formatCurrency(totalExposure)}
          subtitle={`${formatPercent(exposurePct / 100)} of equity`}
          icon={<DollarSign className="h-5 w-5" />}
          color={exposurePct > 40 ? 'yellow' : 'aurora'}
        />
        <SummaryStat
          title="Unrealized P&L"
          value={formatCurrency(totalUnrealizedPnL)}
          subtitle={totalUnrealizedPnL >= 0 ? 'Profit' : 'Loss'}
          icon={<TrendingUp className="h-5 w-5" />}
          color={totalUnrealizedPnL >= 0 ? 'green' : 'red'}
          trend={totalUnrealizedPnL}
        />
        <SummaryStat
          title="LONG / SHORT"
          value={`${groupedByDirection.LONG.length} / ${groupedByDirection.SHORT.length}`}
          icon={groupedByDirection.LONG.length > groupedByDirection.SHORT.length ? 
            <TrendingUp className="h-5 w-5 text-green-400" /> : 
            <TrendingDown className="h-5 w-5 text-red-400" />
          }
          color="neutral"
        />
      </div>

      {/* Positions List */}
      {positions.length === 0 ? (
        <Card variant="elevated" padding="lg">
          <div className="text-center py-12">
            <AlertCircle className="h-12 w-12 mx-auto mb-3 text-gray-600" />
            <p className="text-gray-400">No open positions</p>
            <p className="text-sm text-gray-600 mt-1">
              Positions will appear here when trades are executed
            </p>
          </div>
        </Card>
      ) : (
        <div className="space-y-3">
          {/* LONG Positions */}
          {groupedByDirection.LONG.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-green-400 mb-2 flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                LONG ({groupedByDirection.LONG.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {groupedByDirection.LONG.map((pos) => (
                  <PositionCard key={pos.position_id} position={pos} />
                ))}
              </div>
            </div>
          )}

          {/* SHORT Positions */}
          {groupedByDirection.SHORT.length > 0 && (
            <div className="mt-4">
              <h2 className="text-sm font-semibold text-red-400 mb-2 flex items-center gap-2">
                <TrendingDown className="h-4 w-4" />
                SHORT ({groupedByDirection.SHORT.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {groupedByDirection.SHORT.map((pos) => (
                  <PositionCard key={pos.position_id} position={pos} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Risk Warning */}
      {exposurePct > 40 && (
        <div className="p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/30 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-yellow-400" />
          <span className="text-xs text-yellow-400">
            High exposure ({formatPercent(exposurePct / 100)} of equity). Consider reducing position sizes.
          </span>
        </div>
      )}
    </div>
  );
}

function SummaryStat({
  title,
  value,
  subtitle,
  icon,
  color,
  trend,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color: 'aurora' | 'green' | 'red' | 'yellow' | 'neutral';
  trend?: number;
}) {
  const colorClasses = {
    aurora: 'text-aurora-400',
    green: 'text-green-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    neutral: 'text-gray-400',
  };

  return (
    <Card variant="elevated" padding="md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-mono font-bold text-white mt-1">{value}</p>
          {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
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
        </div>
      )}
    </Card>
  );
}