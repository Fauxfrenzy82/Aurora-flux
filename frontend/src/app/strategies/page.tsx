'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { StrategyTable } from '@/components/StrategyTable';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dna, TrendingUp, Target, Award } from 'lucide-react';

export default function StrategiesPage() {
  const { strategies, performance } = useSystemStore();

  const activeCount = strategies.filter(s => s.status === 'ACTIVE').length;
  const testingCount = strategies.filter(s => s.status === 'TESTING').length;
  const suspendedCount = strategies.filter(s => s.status === 'SUSPENDED').length;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">Strategies</h1>
        <p className="text-sm text-gray-400">View and manage the evolving strategy pool</p>
      </div>

      {/* Strategy Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StrategyStat
          label="Total"
          value={strategies.length}
          icon={<Dna className="h-4 w-4" />}
          color="aurora"
        />
        <StrategyStat
          label="Active"
          value={activeCount}
          icon={<TrendingUp className="h-4 w-4" />}
          color="green"
        />
        <StrategyStat
          label="Testing"
          value={testingCount}
          icon={<Target className="h-4 w-4" />}
          color="yellow"
        />
        <StrategyStat
          label="Suspended"
          value={suspendedCount}
          icon={<Award className="h-4 w-4" />}
          color="red"
        />
      </div>

      {/* Global Performance Summary */}
      {performance && performance.total_trades > 0 && (
        <Card variant="bordered" padding="md">
          <CardHeader>
            <CardTitle>Global Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-gray-500">Total Trades</p>
                <p className="text-lg font-mono font-bold text-white">{performance.total_trades}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Win Rate</p>
                <p className="text-lg font-mono font-bold text-white">{(performance.win_rate * 100).toFixed(1)}%</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Profit Factor</p>
                <p className="text-lg font-mono font-bold text-white">{performance.profit_factor.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Net P&L</p>
                <p className={cn('text-lg font-mono font-bold', performance.net_pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                  {performance.net_pnl >= 0 ? '+' : ''}{performance.net_pnl.toFixed(2)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Strategy Table */}
      <StrategyTable />
    </div>
  );
}

function StrategyStat({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: 'aurora' | 'green' | 'yellow' | 'red';
}) {
  const colorClasses = {
    aurora: 'bg-aurora-600/20 text-aurora-400',
    green: 'bg-green-600/20 text-green-400',
    yellow: 'bg-yellow-600/20 text-yellow-400',
    red: 'bg-red-600/20 text-red-400',
  };

  return (
    <Card variant="default" padding="md">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-xl font-mono font-bold text-white">{value}</p>
        </div>
        <div className={cn('p-2 rounded-lg', colorClasses[color])}>
          {icon}
        </div>
      </div>
    </Card>
  );
}