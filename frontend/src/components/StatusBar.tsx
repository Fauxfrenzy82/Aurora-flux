'use client';

import React from 'react';
import { useSystemStore } from '@/stores/useSystemStore';
import { Badge } from '@/components/ui/badge';
import { cn, formatCurrency, formatPercent, formatDuration } from '@/lib/utils';
import {
  Wifi,
  WifiOff,
  Activity,
  Shield,
  ShieldAlert,
  Zap,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  Layers,
} from 'lucide-react';

export function StatusBar() {
  const {
    isConnected,
    equity,
    mode,
    phaseDay,
    regime,
    session,
    halted,
    scalpModeActive,
    drawdownPct,
    positions,
    uptimeSeconds,
  } = useSystemStore();

  const getRegimeIcon = () => {
    if (regime.includes('TRENDING_UP') || regime.includes('STRONG_TREND_UP'))
      return <TrendingUp className="h-3 w-3" />;
    if (regime.includes('TRENDING_DOWN') || regime.includes('STRONG_TREND_DOWN'))
      return <TrendingDown className="h-3 w-3" />;
    if (regime.includes('RANGE'))
      return <Minus className="h-3 w-3" />;
    return <Activity className="h-3 w-3" />;
  };

  const getRegimeVariant = (): 'success' | 'danger' | 'warning' | 'info' | 'neutral' => {
    if (regime.includes('TRENDING_UP') || regime.includes('STRONG_TREND_UP')) return 'success';
    if (regime.includes('TRENDING_DOWN') || regime.includes('STRONG_TREND_DOWN')) return 'danger';
    if (regime.includes('RANGE')) return 'warning';
    if (regime.includes('VOLATILITY')) return 'info';
    return 'neutral';
  };

  const getSessionColor = () => {
    switch (session) {
      case 'LONDON':
        return 'text-blue-400';
      case 'NEW_YORK':
        return 'text-orange-400';
      case 'OVERLAP':
        return 'text-purple-400';
      case 'ASIAN':
        return 'text-yellow-400';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="sticky top-0 z-50 bg-surface-900/95 backdrop-blur-md border-b border-surface-700">
      <div className="flex items-center justify-between px-4 py-2 gap-2 overflow-x-auto">
        {/* Left Section */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Connection */}
          <div className="flex items-center gap-1.5">
            {isConnected ? (
              <Wifi className="h-3.5 w-3.5 text-green-400" />
            ) : (
              <WifiOff className="h-3.5 w-3.5 text-red-400 animate-pulse" />
            )}
            <span className="text-xs text-gray-400 hidden sm:inline">
              {isConnected ? 'Live' : 'Offline'}
            </span>
          </div>

          {/* Equity */}
          <div className="flex items-center gap-1">
            <span className="text-xs text-gray-500 hidden sm:inline">Equity</span>
            <span className="text-sm font-mono font-bold text-white tabular-nums">
              {formatCurrency(equity)}
            </span>
          </div>

          {/* Daily P&L */}
          {useSystemStore.getState().dailyPnL !== 0 && (
            <span
              className={cn(
                'text-xs font-mono tabular-nums',
                useSystemStore.getState().dailyPnL >= 0 ? 'text-green-400' : 'text-red-400'
              )}
            >
              {useSystemStore.getState().dailyPnL >= 0 ? '+' : ''}
              {formatCurrency(useSystemStore.getState().dailyPnL)}
            </span>
          )}
        </div>

        {/* Center Section */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Mode */}
          <Badge
            variant={mode === 'PHASE' ? 'info' : 'warning'}
            size="sm"
          >
            {mode === 'PHASE' ? `Day ${phaseDay}/5` : 'FREEDOM'}
          </Badge>

          {/* Regime */}
          <Badge variant={getRegimeVariant()} size="sm" dot>
            <span className="flex items-center gap-1">
              {getRegimeIcon()}
              <span className="hidden sm:inline">{regime.replace(/_/g, ' ')}</span>
            </span>
          </Badge>

          {/* Session */}
          <span className={cn('text-xs font-medium', getSessionColor())}>
            <Clock className="h-3 w-3 inline mr-0.5" />
            {session}
          </span>

          {/* Halted */}
          {halted && (
            <Badge variant="danger" size="sm" dot pulse>
              <ShieldAlert className="h-3 w-3" />
              <span className="hidden sm:inline">HALTED</span>
            </Badge>
          )}

          {/* Scalp Mode */}
          {scalpModeActive && (
            <Badge variant="warning" size="sm" dot pulse>
              <Zap className="h-3 w-3" />
              <span className="hidden sm:inline">SCALP</span>
            </Badge>
          )}
        </div>

        {/* Right Section */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Positions */}
          <div className="flex items-center gap-1">
            <Layers className="h-3.5 w-3.5 text-gray-400" />
            <span className="text-xs text-gray-400 tabular-nums">
              {positions.length}
            </span>
          </div>

          {/* Drawdown */}
          <div className="flex items-center gap-1">
            <Shield className="h-3.5 w-3.5 text-gray-400" />
            <span
              className={cn(
                'text-xs font-mono tabular-nums',
                drawdownPct > 0.05 ? 'text-red-400' : drawdownPct > 0.03 ? 'text-yellow-400' : 'text-gray-400'
              )}
            >
              DD {formatPercent(drawdownPct)}
            </span>
          </div>

          {/* Uptime */}
          <span className="text-xs text-gray-500 hidden md:inline tabular-nums">
            {formatDuration(uptimeSeconds || 0)}
          </span>
        </div>
      </div>
    </div>
  );
}