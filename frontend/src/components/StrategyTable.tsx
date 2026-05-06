'use client';

import React, { useState, useMemo } from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn, formatPercent } from '@/lib/utils';
import type { Strategy, StrategyStatus } from '@/types';
import {
  Dna,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  Search,
  Filter,
  Zap,
  Skull,
  Play,
  Pause,
  Trash2,
} from 'lucide-react';

type SortField = 'win_rate' | 'profit_factor' | 'sharpe_ratio' | 'total_trades' | 'generation';
type SortDirection = 'asc' | 'desc';

export function StrategyTable() {
  const { strategies, selectedStrategy, setSelectedStrategy } = useSystemStore();
  const [statusFilter, setStatusFilter] = useState<StrategyStatus | 'ALL'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<SortField>('profit_factor');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const filteredStrategies = useMemo(() => {
    let filtered = [...strategies];

    // Filter by status
    if (statusFilter !== 'ALL') {
      filtered = filtered.filter((s) => s.status === statusFilter);
    }

    // Filter by search
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (s) =>
          s.strategy_name.toLowerCase().includes(query) ||
          s.strategy_id.toLowerCase().includes(query)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      const aVal = a[sortField] || 0;
      const bVal = b[sortField] || 0;
      return sortDirection === 'desc' ? bVal - aVal : aVal - bVal;
    });

    return filtered;
  }, [strategies, statusFilter, searchQuery, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const getStatusBadge = (status: StrategyStatus) => {
    switch (status) {
      case 'ACTIVE':
        return <Badge variant="success" size="sm" dot>ACTIVE</Badge>;
      case 'TESTING':
        return <Badge variant="info" size="sm">TESTING</Badge>;
      case 'SUSPENDED':
        return <Badge variant="warning" size="sm" dot pulse>SUSPENDED</Badge>;
      case 'RETIRED':
        return <Badge variant="neutral" size="sm">RETIRED</Badge>;
    }
  };

  const getBirthBadge = (birthType: string | null) => {
    switch (birthType) {
      case 'SEED':
        return <Badge variant="neutral" size="sm">🌱 Seed</Badge>;
      case 'BRED':
        return <Badge variant="info" size="sm">🧬 Bred</Badge>;
      case 'MUTATED':
        return <Badge variant="warning" size="sm">⚡ Mutant</Badge>;
      default:
        return null;
    }
  };

  const SortHeader = ({
    field,
    children,
  }: {
    field: SortField;
    children: React.ReactNode;
  }) => (
    <th
      className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-200 transition-colors"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        <ArrowUpDown className="h-3 w-3" />
      </div>
    </th>
  );

  return (
    <Card variant="elevated" padding="md" className="h-full">
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Dna className="h-4 w-4 text-purple-400" />
            Strategy Pool
          </span>
        </CardTitle>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">
            {filteredStrategies.length}/{strategies.length}
          </span>
        </div>
      </CardHeader>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-500" />
          <input
            type="text"
            placeholder="Search strategies..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-7 pr-3 py-1.5 text-xs bg-surface-700 border border-surface-600 rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:border-aurora-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StrategyStatus | 'ALL')}
          className="px-2 py-1.5 text-xs bg-surface-700 border border-surface-600 rounded-lg text-gray-200 focus:outline-none focus:border-aurora-500"
        >
          <option value="ALL">All Status</option>
          <option value="ACTIVE">Active</option>
          <option value="TESTING">Testing</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="RETIRED">Retired</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-700">
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Name
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <SortHeader field="win_rate">Win Rate</SortHeader>
              <SortHeader field="profit_factor">PF</SortHeader>
              <SortHeader field="sharpe_ratio">Sharpe</SortHeader>
              <SortHeader field="total_trades">Trades</SortHeader>
              <SortHeader field="generation">Gen</SortHeader>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Origin
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredStrategies.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-8 text-gray-500">
                  <Dna className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No strategies found</p>
                </td>
              </tr>
            ) : (
              filteredStrategies.slice(0, 50).map((strategy) => (
                <StrategyRow
                  key={strategy.strategy_id}
                  strategy={strategy}
                  isSelected={selectedStrategy?.strategy_id === strategy.strategy_id}
                  onSelect={() =>
                    setSelectedStrategy(
                      selectedStrategy?.strategy_id === strategy.strategy_id
                        ? null
                        : strategy
                    )
                  }
                  getStatusBadge={getStatusBadge}
                  getBirthBadge={getBirthBadge}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Selected Strategy DNA Modal */}
      {selectedStrategy && (
        <StrategyDNAModal
          strategy={selectedStrategy}
          onClose={() => setSelectedStrategy(null)}
        />
      )}
    </Card>
  );
}

function StrategyRow({
  strategy,
  isSelected,
  onSelect,
  getStatusBadge,
  getBirthBadge,
}: {
  strategy: Strategy;
  isSelected: boolean;
  onSelect: () => void;
  getStatusBadge: (status: StrategyStatus) => React.ReactNode;
  getBirthBadge: (birthType: string | null) => React.ReactNode;
}) {
  return (
    <tr
      className={cn(
        'border-b border-surface-700/50 transition-colors cursor-pointer',
        'hover:bg-surface-700/50',
        isSelected && 'bg-aurora-600/10'
      )}
      onClick={onSelect}
    >
      <td className="px-3 py-2">
        <div>
          <p className="text-sm text-white font-medium truncate max-w-[150px]">
            {strategy.strategy_name}
          </p>
          <p className="text-xs text-gray-500 font-mono">{strategy.strategy_id}</p>
        </div>
      </td>
      <td className="px-3 py-2">{getStatusBadge(strategy.status)}</td>
      <td className="px-3 py-2">
        <div className="w-20">
          <Progress
            value={(strategy.win_rate || 0) * 100}
            variant={
              (strategy.win_rate || 0) >= 0.55
                ? 'success'
                : (strategy.win_rate || 0) >= 0.4
                  ? 'warning'
                  : 'danger'
            }
            size="sm"
            showLabel
            labelFormat="percent"
          />
        </div>
      </td>
      <td className="px-3 py-2">
        <span
          className={cn(
            'text-sm font-mono font-bold',
            (strategy.profit_factor || 0) >= 1.5
              ? 'text-green-400'
              : (strategy.profit_factor || 0) >= 1.0
                ? 'text-yellow-400'
                : 'text-red-400'
          )}
        >
          {(strategy.profit_factor || 0).toFixed(2)}
        </span>
      </td>
      <td className="px-3 py-2 text-sm font-mono text-gray-300">
        {(strategy.sharpe_ratio || 0).toFixed(2)}
      </td>
      <td className="px-3 py-2 text-sm font-mono text-gray-300">
        {strategy.total_trades}
      </td>
      <td className="px-3 py-2 text-sm font-mono text-gray-300">
        Gen {strategy.generation}
      </td>
      <td className="px-3 py-2">{getBirthBadge(strategy.birth_type)}</td>
    </tr>
  );
}

function StrategyDNAModal({
  strategy,
  onClose,
}: {
  strategy: Strategy;
  onClose: () => void;
}) {
  const dna = strategy.dna;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface-800 border border-surface-600 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto animate-slide-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">{strategy.strategy_name}</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <p className="text-xs text-gray-500">Strategy ID</p>
            <p className="text-sm font-mono text-gray-300">{strategy.strategy_id}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Status</p>
            <Badge
              variant={
                strategy.status === 'ACTIVE'
                  ? 'success'
                  : strategy.status === 'SUSPENDED'
                    ? 'warning'
                    : 'neutral'
              }
              size="sm"
            >
              {strategy.status}
            </Badge>
          </div>
          <div>
            <p className="text-xs text-gray-500">Timeframe</p>
            <p className="text-sm text-gray-300">{dna?.tf || 'N/A'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Confirmation TF</p>
            <p className="text-sm text-gray-300">{dna?.confirm_tf || 'N/A'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Regime Preference</p>
            <p className="text-sm text-gray-300">{dna?.regime || 'ALL'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Session Preference</p>
            <p className="text-sm text-gray-300">{dna?.session || 'ALL'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Aggression</p>
            <Progress value={(dna?.aggression || 0) * 100} size="sm" />
          </div>
          <div>
            <p className="text-xs text-gray-500">Max Holding</p>
            <p className="text-sm text-gray-300">{dna?.holding_min || 0} min</p>
          </div>
        </div>

        {/* Entry Conditions */}
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-gray-300 mb-2">Entry Conditions</h4>
          {dna?.entry?.length ? (
            <div className="space-y-1">
              {dna.entry.map((cond, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 p-2 bg-surface-700 rounded-lg text-xs"
                >
                  <Badge variant="info" size="sm">
                    {cond.indicator}
                  </Badge>
                  <span className="text-gray-400">{cond.operator}</span>
                  <span className="text-white font-mono">{cond.value}</span>
                  <span className="text-gray-500">@{cond.timeframe}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500">No entry conditions defined</p>
          )}
        </div>

        {/* Exit Conditions */}
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-gray-300 mb-2">Exit Conditions</h4>
          {dna?.exit?.length ? (
            <div className="space-y-1">
              {dna.exit.map((cond, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 p-2 bg-surface-700 rounded-lg text-xs"
                >
                  <Badge variant="warning" size="sm">
                    {cond.indicator}
                  </Badge>
                  <span className="text-gray-400">{cond.operator}</span>
                  <span className="text-white font-mono">{cond.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500">No exit conditions defined</p>
          )}
        </div>

        {/* Risk Parameters */}
        <div>
          <h4 className="text-sm font-semibold text-gray-300 mb-2">Risk Parameters</h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 bg-surface-700 rounded-lg">
              <span className="text-gray-500">Stop Loss: </span>
              <span className="text-gray-300">
                {dna?.stop?.method} x{dna?.stop?.value}
              </span>
            </div>
            <div className="p-2 bg-surface-700 rounded-lg">
              <span className="text-gray-500">Take Profit: </span>
              <span className="text-gray-300">
                {dna?.profit?.method} x{dna?.profit?.value}
              </span>
            </div>
            <div className="p-2 bg-surface-700 rounded-lg">
              <span className="text-gray-500">Pyramiding: </span>
              <span className={dna?.pyramiding ? 'text-green-400' : 'text-gray-500'}>
                {dna?.pyramiding ? `Yes (max ${dna?.max_layers} layers)` : 'No'}
              </span>
            </div>
            <div className="p-2 bg-surface-700 rounded-lg">
              <span className="text-gray-500">Hedging: </span>
              <span className={dna?.hedging ? 'text-yellow-400' : 'text-gray-500'}>
                {dna?.hedging ? 'Yes' : 'No'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}