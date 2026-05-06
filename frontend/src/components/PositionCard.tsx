'use client';

import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn, formatCurrency, formatPips, formatTimeAgo } from '@/lib/utils';
import type { Position } from '@/types';
import {
  TrendingUp,
  TrendingDown,
  Target,
  Shield,
  Layers,
} from 'lucide-react';

interface PositionCardProps {
  position: Position;
  onClick?: () => void;
}

export function PositionCard({ position, onClick }: PositionCardProps) {
  const {
    symbol,
    direction,
    entry_price,
    current_price,
    stop_loss,
    take_profit,
    unrealized_pips,
    profit,
    volume,
    comment,
    open_time,
  } = position;

  const isLong = direction === 'LONG';
  const isProfitable = unrealized_pips >= 0;

  // Calculate progress toward take profit
  const entryToTarget = take_profit
    ? Math.abs(take_profit - entry_price)
    : 0;
  const currentProgress = take_profit
    ? Math.abs(current_price - entry_price)
    : 0;
  const progressPercent = entryToTarget > 0
    ? Math.min(100, (currentProgress / entryToTarget) * 100)
    : 0;

  // Calculate stop loss position as marker
  const totalRange = take_profit && stop_loss
    ? Math.abs(take_profit - stop_loss)
    : 0;
  const slMarker = take_profit && stop_loss && totalRange > 0
    ? (Math.abs(stop_loss - entry_price) / totalRange) * 100
    : 0;

  // Extract strategy name from comment
  const strategyName = comment?.replace('AF_', '') || 'Unknown';

  // Check for pyramid layer indicator
  const hasPyramid = comment?.includes('LAYER');

  return (
    <Card
      variant="bordered"
      padding="md"
      hover
      onClick={onClick}
      className="animate-slide-up"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-white font-mono">{symbol}</span>
          <Badge
            variant={isLong ? 'success' : 'danger'}
            size="sm"
            dot
          >
            {isLong ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <TrendingDown className="h-3 w-3" />
            )}
            {direction}
          </Badge>
          {hasPyramid && (
            <Badge variant="warning" size="sm">
              <Layers className="h-3 w-3" />
            </Badge>
          )}
        </div>
        <span className="text-xs text-gray-500">{formatTimeAgo(open_time)}</span>
      </div>

      {/* P&L */}
      <div className="flex items-center justify-between mb-3">
        <span
          className={cn(
            'text-lg font-mono font-bold tabular-nums',
            isProfitable ? 'text-green-400' : 'text-red-400'
          )}
        >
          {isProfitable ? '+' : ''}
          {formatPips(unrealized_pips)}
        </span>
        <span
          className={cn(
            'text-sm font-mono tabular-nums',
            profit >= 0 ? 'text-green-400' : 'text-red-400'
          )}
        >
          {profit >= 0 ? '+' : ''}
          {formatCurrency(profit)}
        </span>
      </div>

      {/* Progress Bar */}
      {take_profit && stop_loss && (
        <div className="mb-2">
          <Progress
            value={progressPercent}
            variant={isProfitable ? 'success' : 'danger'}
            size="sm"
            showLabel={false}
            marker={slMarker}
            markerLabel={`SL: ${stop_loss.toFixed(5)}`}
          />
          <div className="flex justify-between mt-1">
            <span className="text-xs text-red-400 font-mono">
              SL {stop_loss.toFixed(5)}
            </span>
            <span className="text-xs text-green-400 font-mono">
              TP {take_profit.toFixed(5)}
            </span>
          </div>
        </div>
      )}

      {/* Details */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-3">
          <span>
            <Shield className="h-3 w-3 inline mr-1" />
            Entry: <span className="text-gray-300 font-mono">{entry_price.toFixed(5)}</span>
          </span>
          <span>
            <Target className="h-3 w-3 inline mr-1" />
            Size: <span className="text-gray-300 font-mono">{volume.toFixed(2)}</span>
          </span>
        </div>
        <span className="text-gray-500 truncate max-w-[120px]">{strategyName}</span>
      </div>
    </Card>
  );
}